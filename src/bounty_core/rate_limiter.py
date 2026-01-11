import asyncio
import time


class RateLimiter:
    """
    A simple token bucket / leaky bucket rate limiter for async operations.
    Ensures a minimum delay between acquisitions.
    """

    def __init__(self, calls_per_second: float = 1.0):
        self.delay = 1.0 / calls_per_second if calls_per_second > 0 else 0
        self.last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """
        Waits until the rate limit allows for a new action.
        Uses a lock to ensure thread/task safety if shared across tasks.
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                wait_time = self.delay - elapsed
                await asyncio.sleep(wait_time)

            # Update last_call after the wait (or immediately if no wait)
            # We use time.time() again to be precise after the sleep
            self.last_call = time.time()
