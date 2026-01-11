import asyncio
import time

import pytest

from bounty_core.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_initialization():
    limiter = RateLimiter(calls_per_second=2.0)
    assert limiter.delay == 0.5
    assert limiter.last_call == 0.0


@pytest.mark.asyncio
async def test_rate_limiter_acquire_wait():
    # 10 calls per second = 0.1s delay
    limiter = RateLimiter(calls_per_second=10.0)

    start = time.time()

    # First call should be instant
    await limiter.acquire()
    t1 = time.time()

    # Second call should wait ~0.1s
    await limiter.acquire()
    t2 = time.time()

    # Check timings with some tolerance for OS scheduling
    assert (t1 - start) < 0.05  # Instant
    assert (t2 - t1) >= 0.09  # Should be at least ~0.1s

    # Third call
    await limiter.acquire()
    t3 = time.time()
    assert (t3 - t2) >= 0.09


@pytest.mark.asyncio
async def test_rate_limiter_concurrency():
    # Test that multiple tasks respect the lock
    limiter = RateLimiter(calls_per_second=20.0)  # 0.05s delay

    async def worker():
        await limiter.acquire()
        return time.time()

    # Launch 3 workers at once
    results = await asyncio.gather(worker(), worker(), worker())

    # They should finish sequentially, separated by delay
    results.sort()

    # Total time should be at least 2 delays (0.1s)
    # 1st: instant (0s), 2nd: 0.05s, 3rd: 0.10s
    assert (results[2] - results[0]) >= 0.09
