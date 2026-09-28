"""
Proactive LLM rate limiter across three independent dimensions: requests per
minute (RPM), requests per day (RPD) and tokens per minute (TPM).

Each call reserves capacity before it is made. The lock is held only while the
windows are checked and updated, never while waiting, so concurrent callers do
not serialize behind one sleeping request. The RPD counter is persisted in the
database to survive restarts.
"""

import asyncio
import datetime
import time
import zoneinfo
from collections import deque
from dataclasses import dataclass, field

import structlog

from app.config import settings
from app.db import crud

log = structlog.get_logger()

WINDOW_SECONDS = 60.0
_SAFETY_MARGIN = 0.1  # seconds added to computed waits


class DailyQuotaExhaustedError(Exception):
    """Raised when the daily RPD quota is exhausted."""


@dataclass
class Reservation:
    """Capacity reserved for one LLM call. `tokens` is corrected after the call."""

    timestamp: float
    tokens: int


@dataclass
class RateLimiterState:
    # RPM: timestamps of the calls in the last 60 seconds
    rpm_window: deque[float] = field(default_factory=deque)

    # RPD: daily counter + reset timestamp
    rpd_count: int = 0
    rpd_reset_at: float = 0.0

    # TPM: reservations of the last 60 seconds
    tpm_window: deque[Reservation] = field(default_factory=deque)


class RateLimiter:
    """Blocks BEFORE provider limits are hit instead of reacting to 429 errors."""

    def __init__(self) -> None:
        self._state = RateLimiterState()
        self._lock = asyncio.Lock()
        self._initialized = False
        self._state.rpd_reset_at = self._next_midnight_pacific()

    async def _init_from_db(self) -> None:
        """Lazy load persisted RPD state from DB on first use."""
        if self._initialized:
            return
        try:
            rpd_count_str = await crud.get_rate_limit_state("rpd_count")
            rpd_reset_at_str = await crud.get_rate_limit_state("rpd_reset_at")
            if rpd_count_str is not None:
                self._state.rpd_count = int(rpd_count_str)
            if rpd_reset_at_str is not None:
                self._state.rpd_reset_at = float(rpd_reset_at_str)
        except Exception as e:
            # Fall back to in-memory defaults if the DB is unavailable during boot
            log.warning("rate_limiter_state_load_failed", error=str(e))
        self._initialized = True

    async def _save_rpd_to_db(self) -> None:
        try:
            await crud.set_rate_limit_state("rpd_count", str(self._state.rpd_count))
            await crud.set_rate_limit_state("rpd_reset_at", str(self._state.rpd_reset_at))
        except Exception as e:
            log.warning("rate_limiter_state_save_failed", error=str(e))

    async def acquire(self, estimated_tokens: int = 500) -> Reservation:
        """Wait until a call fits within every limit, then reserve it.

        Raises DailyQuotaExhaustedError when the daily quota is used up, since
        waiting a few seconds cannot fix that.
        """
        while True:
            async with self._lock:
                await self._init_from_db()
                now = time.time()
                self._refresh_windows(now)

                if self._state.rpd_count >= settings.RATE_LIMIT_RPD_MAX:
                    reset_in = self._state.rpd_reset_at - now
                    raise DailyQuotaExhaustedError(
                        f"Daily quota exhausted. Resets in {reset_in / 3600:.1f} hours."
                    )

                wait = self._required_wait(now, estimated_tokens)
                if wait <= 0:
                    reservation = Reservation(timestamp=now, tokens=estimated_tokens)
                    self._state.rpm_window.append(now)
                    self._state.tpm_window.append(reservation)
                    self._state.rpd_count += 1
                    await self._save_rpd_to_db()
                    return reservation
            # Sleep without holding the lock
            await asyncio.sleep(wait)

    async def record_actual_tokens(self, reservation: Reservation, actual_tokens: int) -> None:
        """Replace the estimate of a reservation with the tokens actually used."""
        async with self._lock:
            reservation.tokens = max(actual_tokens, 0)

    def _required_wait(self, now: float, tokens: int) -> float:
        """Seconds until a call of `tokens` fits in both per-minute windows (0 if now)."""
        waits = [0.0]

        if len(self._state.rpm_window) >= settings.RATE_LIMIT_RPM_MAX:
            waits.append(self._state.rpm_window[0] + WINDOW_SECONDS - now + _SAFETY_MARGIN)

        used = sum(r.tokens for r in self._state.tpm_window)
        excess = used + tokens - settings.RATE_LIMIT_TPM_MAX
        if excess > 0 and self._state.tpm_window:
            # Wait until enough of the oldest reservations leave the window.
            # A single call larger than the whole budget only waits for an empty window.
            freed = 0
            for reservation in self._state.tpm_window:
                freed += reservation.tokens
                if freed >= excess:
                    break
            waits.append(reservation.timestamp + WINDOW_SECONDS - now + _SAFETY_MARGIN)

        return max(waits)

    def _refresh_windows(self, now: float) -> None:
        """Drop entries older than the window and reset the daily counter at midnight."""
        cutoff = now - WINDOW_SECONDS
        while self._state.rpm_window and self._state.rpm_window[0] < cutoff:
            self._state.rpm_window.popleft()
        while self._state.tpm_window and self._state.tpm_window[0].timestamp < cutoff:
            self._state.tpm_window.popleft()

        # Reset RPD at Pacific midnight (Gemini quotas reset then)
        if now >= self._state.rpd_reset_at:
            self._state.rpd_count = 0
            self._state.rpd_reset_at = self._next_midnight_pacific()

    async def get_status(self) -> dict:
        """Returns the current rate limiter state for the frontend."""
        await self._init_from_db()
        now = time.time()
        self._refresh_windows(now)
        return {
            "rpm_used": len(self._state.rpm_window),
            "rpm_max": settings.RATE_LIMIT_RPM_MAX,
            "rpd_used": self._state.rpd_count,
            "rpd_max": settings.RATE_LIMIT_RPD_MAX,
            "tpm_used": sum(r.tokens for r in self._state.tpm_window),
            "tpm_max": settings.RATE_LIMIT_TPM_MAX,
            "rpd_resets_at": self._state.rpd_reset_at,
        }

    @staticmethod
    def _next_midnight_pacific() -> float:
        """Returns the Unix timestamp of the next Pacific midnight (UTC-8)."""
        tz: datetime.tzinfo
        try:
            tz = zoneinfo.ZoneInfo("America/Los_Angeles")
        except Exception:
            # Fallback: UTC-8
            tz = datetime.timezone(datetime.timedelta(hours=-8))
        now_pacific = datetime.datetime.now(tz)
        midnight = (now_pacific + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return midnight.timestamp()


# Singleton instance
rate_limiter = RateLimiter()
