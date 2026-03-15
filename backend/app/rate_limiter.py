"""
Token bucket rate limiter across three independent dimensions (RPM, RPD, TPM).
Thread-safe via asyncio.Lock. RPD counter persisted in SQLite to survive restarts.
"""

import asyncio
import datetime
import time
import zoneinfo
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings
from app.db import crud


class DailyQuotaExhaustedError(Exception):
    """Raised when the daily RPD quota is exhausted."""
    pass


@dataclass
class RateLimiterState:
    # RPM: sliding window over the last 60 seconds
    rpm_window: deque = field(default_factory=deque)

    # RPD: daily counter + reset timestamp
    rpd_count: int = 0
    rpd_reset_at: float = 0.0

    # TPM: sliding window of (timestamp, token_count) over the last 60 seconds
    tpm_window: deque = field(default_factory=deque)


class RateLimiter:
    """
    Proactive rate limiter that blocks BEFORE hitting Google API limits.
    Three independent dimensions: RPM, RPD, TPM.
    """

    def __init__(self):
        self._state = RateLimiterState()
        self._lock = asyncio.Lock()
        self._initialized = False
        # Initialize RPD reset time
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
        except Exception:
            pass  # Fallback to in-memory defaults if DB fails during boot
            
        self._initialized = True

    async def _save_rpd_to_db(self) -> None:
        """Persist RPD state to DB."""
        try:
            await crud.set_rate_limit_state("rpd_count", str(self._state.rpd_count))
            await crud.set_rate_limit_state("rpd_reset_at", str(self._state.rpd_reset_at))
        except Exception:
            pass

    async def acquire(self, estimated_tokens: int = 500) -> None:
        """
        Blocks until it is safe to make an API call.
        Raises DailyQuotaExhaustedError if daily RPD quota is exhausted.
        """
        async with self._lock:
            await self._init_from_db()
            now = time.time()
            self._refresh_windows(now)

            # Check RPD (daily limit — cannot recover by waiting)
            if self._state.rpd_count >= settings.RATE_LIMIT_RPD_MAX:
                reset_in = self._state.rpd_reset_at - now
                raise DailyQuotaExhaustedError(
                    f"Daily quota exhausted. Resets in {reset_in / 3600:.1f} hours."
                )

            # Check RPM — wait if necessary
            await self._wait_for_rpm_capacity(now)

            # Check TPM — wait if necessary
            now = time.time()
            self._refresh_windows(now)
            await self._wait_for_tpm_capacity(now, estimated_tokens)

            # Record the request
            now = time.time()
            self._state.rpm_window.append(now)
            self._state.tpm_window.append((now, estimated_tokens))
            self._state.rpd_count += 1
            
            # Save RPD update to DB
            await self._save_rpd_to_db()

    async def record_actual_tokens(self, actual_tokens: int, estimated_tokens: int = 500) -> None:
        """Update the TPM window with actual token usage after an API call."""
        now = time.time()
        # Adjust the last entry if it exists
        if self._state.tpm_window:
            ts, _ = self._state.tpm_window[-1]
            self._state.tpm_window[-1] = (ts, actual_tokens)

    def _refresh_windows(self, now: float) -> None:
        """Remove entries older than 60 seconds from the sliding windows."""
        cutoff = now - 60
        while self._state.rpm_window and self._state.rpm_window[0] < cutoff:
            self._state.rpm_window.popleft()
        while self._state.tpm_window and self._state.tpm_window[0][0] < cutoff:
            self._state.tpm_window.popleft()

        # Reset RPD at Pacific midnight
        if now >= self._state.rpd_reset_at:
            self._state.rpd_count = 0
            self._state.rpd_reset_at = self._next_midnight_pacific()
            # If we are in an async context, we could save here, but we'll 
            # let acquire() or the next operation trigger the save.

    async def _wait_for_rpm_capacity(self, now: float) -> None:
        """Wait until RPM has capacity."""
        while len(self._state.rpm_window) >= settings.RATE_LIMIT_RPM_MAX:
            oldest = self._state.rpm_window[0]
            wait = (oldest + 60) - now + 0.1  # 100ms buffer
            if wait > 0:
                await asyncio.sleep(wait)
            now = time.time()
            self._refresh_windows(now)

    async def _wait_for_tpm_capacity(self, now: float, tokens: int) -> None:
        """Wait until TPM has capacity for the estimated tokens."""
        current_tpm = sum(t for _, t in self._state.tpm_window)
        while current_tpm + tokens > settings.RATE_LIMIT_TPM_MAX:
            if self._state.tpm_window:
                oldest_ts = self._state.tpm_window[0][0]
                wait = (oldest_ts + 60) - now + 0.1
                if wait > 0:
                    await asyncio.sleep(wait)
            else:
                break
            now = time.time()
            self._refresh_windows(now)
            current_tpm = sum(t for _, t in self._state.tpm_window)

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
            "tpm_used": sum(t for _, t in self._state.tpm_window),
            "tpm_max": settings.RATE_LIMIT_TPM_MAX,
            "rpd_resets_at": self._state.rpd_reset_at,
        }

    @staticmethod
    def _next_midnight_pacific() -> float:
        """Returns the Unix timestamp of the next Pacific midnight (UTC-8)."""
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
