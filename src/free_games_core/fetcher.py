import asyncio
import re
from typing import List, Dict
import aiohttp
import logging

logger = logging.getLogger(__name__)

BLUESKY_FEED_URL = "https://freegamefindings.bsky.social/feed"  # placeholder; replace with real endpoint


async def fetch_bsky_feed(session: aiohttp.ClientSession, limit: int = 50) -> List[Dict]:
    """
    Fetches the Bluesky feed (skeleton).
    Returns a list of post dicts with keys: 'uri', 'text'.
    NOTE: Replace with real Bluesky API calls as needed.
    """
    try:
        async with session.get(BLUESKY_FEED_URL, timeout=20) as resp:
            if resp.status != 200:
                logger.warning("Bluesky feed request returned %s", resp.status)
                return []
            data = await resp.json()  # shape depends on actual endpoint
            # For now, attempt to normalise a common shape if possible
            posts = []
            # If data is already a list of posts:
            if isinstance(data, list):
                for item in data[:limit]:
                    post = {"uri": item.get("uri"), "text": item.get("text") or ""}
                    posts.append(post)
            elif isinstance(data, dict) and "posts" in data:
                for item in data["posts"][:limit]:
                    posts.append({"uri": item.get("uri"), "text": item.get("text") or ""})
            else:
                logger.debug("Unexpected Bluesky feed shape")
            return posts
    except Exception as e:
        logger.exception("Failed to fetch Bluesky feed: %s", e)
        return []


URL_RE = re.compile(r"https?://[^\s)>\]]+")


def extract_links_from_text(text: str) -> List[str]:
    """Simple link extractor from text."""
    return URL_RE.findall(text or "")