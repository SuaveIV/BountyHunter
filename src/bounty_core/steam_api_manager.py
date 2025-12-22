import asyncio
import time
import random
import logging
from typing import Optional, Any

import aiohttp

logger = logging.getLogger(__name__)


class SteamAPIManager:
    """
    Async Steam API helper with simple rate limiting and retry/backoff.

    Notes:
    - Uses aiohttp and is async-only.
    - Keep one manager instance per running bot (or pass a shared aiohttp.ClientSession).
    - Call `await manager.close()` on shutdown if the manager created its own session.
    """

    # Rate limiting (seconds)
    STEAM_API_RATE_LIMIT = 3.0
    STEAM_STORE_API_RATE_LIMIT = 2.0
    FULL_SCAN_RATE_LIMIT = 5.0

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        max_retries: int = 3,
        base_backoff: float = 1.0,
    ):
        self._session = session
        self._last_steam_api_call = 0.0
        self._last_steam_store_api_call = 0.0
        self.max_retries = max_retries
        self.base_backoff = base_backoff

    async def ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def rate_limit_steam_api(self) -> None:
        """Rate limit for non-storefront Steam API calls."""
        now = time.time()
        delta = now - self._last_steam_api_call
        if delta < self.STEAM_API_RATE_LIMIT:
            wait = self.STEAM_API_RATE_LIMIT - delta
            logger.debug("Rate-limiting Steam API call for %.2fs", wait)
            await asyncio.sleep(wait)
        self._last_steam_api_call = time.time()

    async def rate_limit_steam_store_api(self) -> None:
        """Rate limit for Steam store (appdetails) calls."""
        now = time.time()
        delta = now - self._last_steam_store_api_call
        if delta < self.STEAM_STORE_API_RATE_LIMIT:
            wait = self.STEAM_STORE_API_RATE_LIMIT - delta
            logger.debug("Rate-limiting Steam store API call for %.2fs", wait)
            await asyncio.sleep(wait)
        self._last_steam_store_api_call = time.time()

    async def rate_limit_full_scan(self) -> None:
        now = time.time()
        delta = now - self._last_steam_store_api_call
        if delta < self.FULL_SCAN_RATE_LIMIT:
            wait = self.FULL_SCAN_RATE_LIMIT - delta
            logger.debug("Rate-limiting full-scan Steam store call for %.2fs", wait)
            await asyncio.sleep(wait)
        self._last_steam_store_api_call = time.time()

    async def make_request_with_retry(
        self, url: str, timeout: int = 10
    ) -> Optional[Any]:
        """
        Fetch JSON from `url` with retry and exponential backoff.

        Returns parsed JSON on success, or None on failure.
        Handles HTTP 429 by backing off and retrying.
        """
        session = await self.ensure_session()

        for attempt in range(self.max_retries + 1):
            try:
                async with session.get(url, timeout=timeout) as resp:
                    status = resp.status
                    if status == 200:
                        # parse as JSON (Steam store returns JSON for appdetails)
                        try:
                            return await resp.json()
                        except Exception:
                            text = await resp.text()
                            logger.debug("Non-JSON response received (len=%d)", len(text))
                            return None
                    elif status == 429:
                        # rate-limited: backoff and retry
                        backoff = self._compute_backoff(attempt)
                        logger.warning(
                            "Steam 429 received, backing off %.2fs (attempt %d)", backoff, attempt
                        )
                        await asyncio.sleep(backoff)
                        continue
                    elif 500 <= status < 600:
                        # server error: retry with backoff
                        backoff = self._compute_backoff(attempt)
                        logger.warning(
                            "Steam server error %d, retrying in %.2fs (attempt %d)",
                            status,
                            backoff,
                            attempt,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        # other non-success status (404, 400, etc.)
                        logger.debug("Steam request returned status %d for %s", status, url)
                        return None
            except asyncio.TimeoutError:
                backoff = self._compute_backoff(attempt)
                logger.warning("Timeout fetching %s, retrying in %.2fs (attempt %d)", url, backoff, attempt)
                await asyncio.sleep(backoff)
                continue
            except Exception as e:
                backoff = self._compute_backoff(attempt)
                logger.exception(
                    "Error fetching %s: %s (attempt %d). Retrying in %.2fs", url, e, attempt, backoff
                )
                await asyncio.sleep(backoff)
                continue

        logger.error("Exceeded retries while fetching %s", url)
        return None

    def _compute_backoff(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        base = self.base_backoff * (2 ** attempt)
        jitter = random.uniform(0, base * 0.1)
        return base + jitter