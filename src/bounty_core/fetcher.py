import asyncio
import logging
import random
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Using a public endpoint for a known deal aggregator or search feed.
# Placeholder actor for now; in production this would be configurable.
TARGET_ACTOR = "freegamefindings.bsky.social"
FEED_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
MAX_RETRIES = 3
BASE_DELAY = 2.0


class BlueskyFetcher:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_latest(self, limit: int = 10) -> list[dict[str, Any]]:
        params = {"actor": TARGET_ACTOR, "limit": limit, "filter": "posts_no_replies"}

        for attempt in range(MAX_RETRIES):
            try:
                async with self.session.get(FEED_URL, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [item["post"] for item in data.get("feed", [])]

                    if resp.status == 429 or 500 <= resp.status < 600:
                        delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                        logger.warning(f"Bluesky fetch failed ({resp.status}). Retrying in {delay:.2f}s...")
                        await asyncio.sleep(delay)
                        continue

                    logger.error(f"Bluesky fetch failed: {resp.status}")
                    return []
            except Exception as e:
                delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                logger.error(f"Exception fetching Bluesky feed: {e}. Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

        logger.error("Max retries exceeded for Bluesky fetcher.")
        return []
