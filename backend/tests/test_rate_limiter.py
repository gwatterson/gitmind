"""Tests for the rate limiter — RPM, RPD, TPM blocking and concurrent access."""

import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock
from app.rate_limiter import RateLimiter, DailyQuotaExhaustedError


@pytest.fixture
def limiter():
    """Fresh rate limiter for each test."""
    with patch("app.rate_limiter.settings") as mock_settings:
        mock_settings.RATE_LIMIT_RPM_MAX = 5
        mock_settings.RATE_LIMIT_RPD_MAX = 10
        mock_settings.RATE_LIMIT_TPM_MAX = 5000
        rl = RateLimiter()
        rl._state.rpd_reset_at = time.time() + 86400  # Far future
        yield rl


@pytest.mark.asyncio
async def test_rpm_blocking(limiter):
    """Verify that the (RPM_MAX + 1)th request is blocked."""
    # Make RPM_MAX requests quickly
    for _ in range(5):
        await limiter.acquire(estimated_tokens=100)

    # The next request should block (or take longer than 0.5s)
    start = time.time()
    # We'll use a short timeout to not actually wait 60s
    try:
        await asyncio.wait_for(limiter.acquire(estimated_tokens=100), timeout=0.5)
        # If we get here, the limiter didn't block — which is wrong
        blocked = False
    except asyncio.TimeoutError:
        blocked = True

    assert blocked, "Rate limiter should block when RPM limit is reached"


@pytest.mark.asyncio
async def test_rpm_release(limiter):
    """Verify that RPM window frees up after entries expire."""
    # Fill the RPM window with old entries
    old_time = time.time() - 61  # Older than 60s
    for _ in range(5):
        limiter._state.rpm_window.append(old_time)

    # These should be cleaned up, so acquire should succeed immediately
    start = time.time()
    await limiter.acquire(estimated_tokens=100)
    elapsed = time.time() - start

    assert elapsed < 1.0, f"Should have acquired immediately after window expiry, took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_rpd_exhaustion(limiter):
    """Verify DailyQuotaExhaustedError is raised when RPD limit is hit."""
    # Manually set RPD count to the limit
    limiter._state.rpd_count = 10

    with pytest.raises(DailyQuotaExhaustedError):
        await limiter.acquire(estimated_tokens=100)


@pytest.mark.asyncio
async def test_tpm_blocking(limiter):
    """Verify blocking when token budget is exceeded."""
    # Add a large token entry
    limiter._state.tpm_window.append((time.time(), 4900))

    # The next request with 200 tokens should be blocked (4900 + 200 > 5000)
    start = time.time()
    try:
        await asyncio.wait_for(limiter.acquire(estimated_tokens=200), timeout=0.5)
        blocked = False
    except asyncio.TimeoutError:
        blocked = True

    assert blocked, "Rate limiter should block when TPM limit is exceeded"


@pytest.mark.asyncio
async def test_concurrent_requests(limiter):
    """20 parallel coroutines — none should exceed limits."""
    results = []
    errors = []

    async def make_request(idx):
        try:
            await asyncio.wait_for(limiter.acquire(estimated_tokens=100), timeout=30)
            results.append(idx)
        except DailyQuotaExhaustedError:
            errors.append(("rpd", idx))
        except asyncio.TimeoutError:
            errors.append(("timeout", idx))

    # Launch 20 concurrent requests — only 5 RPM should go through immediately
    # and 10 RPD total
    tasks = [make_request(i) for i in range(20)]
    await asyncio.wait(tasks, timeout=5)

    # At most RPD_MAX (10) should succeed
    assert len(results) <= 10, f"Expected at most 10 successes, got {len(results)}"


@pytest.mark.asyncio
async def test_get_status(limiter):
    """Verify status returns correct structure."""
    await limiter.acquire(estimated_tokens=500)
    status = limiter.get_status()

    assert "rpm_used" in status
    assert "rpm_max" in status
    assert "rpd_used" in status
    assert "rpd_max" in status
    assert "tpm_used" in status
    assert "tpm_max" in status
    assert status["rpm_used"] == 1
    assert status["rpd_used"] == 1
    assert status["tpm_used"] == 500
