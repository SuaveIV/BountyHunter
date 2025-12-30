import asyncio
import logging
import random
from typing import Any

import aiohttp
import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FEED_URL = "https://www.reddit.com/r/FreeGameFindings/new/.rss"
MAX_RETRIES = 3
BASE_DELAY = 2.0
TARGET_ACTOR = "r/FreeGameFindings"


class RedditRSSFetcher:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_latest(self, limit: int = 10) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": "BountyHunter/1.0 (Discord Bot; +https://github.com/yourusername/BountyHunter)"
        }

        for attempt in range(MAX_RETRIES):
            try:
                # We fetch the content as text first, then pass to feedparser
                # feedparser can fetch URL directly, but using aiohttp keeps it async
                async with self.session.get(FEED_URL, headers=headers) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        # feedparser.parse can take a string
                        feed = feedparser.parse(content)

                        posts = []
                        for entry in feed.entries[:limit]:
                            post = self._parse_entry(entry)
                            if post:
                                posts.append(post)
                        return posts

                    if resp.status == 429 or 500 <= resp.status < 600:
                        delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                        logger.warning(
                            f"Reddit RSS fetch failed ({resp.status}). Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue

                    logger.error(f"Reddit RSS fetch failed: {resp.status}")
                    return []
            except Exception as e:
                delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                logger.error(f"Exception fetching Reddit RSS: {e}. Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

        logger.error("Max retries exceeded for Reddit RSS fetcher.")
        return []

    def _parse_entry(self, entry: Any) -> dict[str, Any] | None:
        try:
            # Basic Fields
            title = entry.get("title", "No Title")
            reddit_link = entry.get("link", "")
            reddit_id = entry.get("id", reddit_link)

            # Content Parsing for External Link and Thumbnail
            content_html = ""
            if "content" in entry:
                content_html = entry.content[0].value
            elif "description" in entry:
                content_html = entry.description

            soup = BeautifulSoup(content_html, "html.parser")

            # Extract External Link
            # r/FreeGameFindings usually has a link with text "[link]"
            external_link = None
            link_tag = soup.find("a", string="[link]")
            if link_tag and link_tag.has_attr("href"):
                external_link = link_tag["href"]
            else:
                # Fallback: find the first link that isn't a reddit link
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "reddit.com" not in href and "redd.it" not in href:
                        external_link = href
                        break

            # If no external link found, use the reddit link (it might be a discussion post)
            if not external_link:
                external_link = reddit_link

            # Extract Thumbnail
            thumbnail = None
            # Check media_thumbnail (feedparser specific)
            if "media_thumbnail" in entry and entry.media_thumbnail:
                thumbnail = entry.media_thumbnail[0]["url"]
            # Fallback to looking for img in content
            if not thumbnail:
                img = soup.find("img")
                if img and img.has_attr("src"):
                    thumbnail = img["src"]

            return {
                "id": reddit_id,
                "title": title,
                "url": reddit_link,  # The Reddit Post URL
                "external_url": external_link,  # The Deal URL
                "thumbnail": thumbnail,
                "date": entry.get("updated") or entry.get("published"),
            }

        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None