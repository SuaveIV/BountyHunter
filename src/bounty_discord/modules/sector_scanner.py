import logging
from typing import Any

from bounty_core.fetcher import RedditRSSFetcher
from bounty_core.parser import (
    determine_content_type,
    extract_epic_slugs,
    extract_gog_urls,
    extract_itch_urls,
    extract_ps_urls,
    extract_steam_ids,
    is_safe_link,
)
from bounty_core.store import Store

logger = logging.getLogger(__name__)


class SectorScanner:
    """
    Scans external sectors (feeds) for bounties (free games).
    """

    def __init__(self, fetcher: RedditRSSFetcher, store: Store):
        self.fetcher = fetcher
        self.store = store

    async def scan(self, limit: int = 10, ignore_seen: bool = False) -> list[tuple[str, dict[str, Any]]]:
        """
        Scans the feed for new deals.
        Returns a list of (uri, parsed_data) tuples for new, unseen posts.
        If ignore_seen is True, returns all fetched posts (useful for testing).
        """
        try:
            posts = await self.fetcher.fetch_latest(limit=limit)
            new_announcements = []

            for post in posts:
                uri = post.get("id")
                if not uri:
                    continue

                # Check if we've already processed this bounty
                if not ignore_seen and await self.store.is_post_seen(uri):
                    continue

                text = post.get("title", "")

                # Determine content type and filter INFO posts
                content_type = determine_content_type(text)
                if content_type == "INFO":
                    logger.debug(f"Skipping INFO post: {text}")
                    if not ignore_seen:
                        await self.store.mark_post_seen(uri)
                    continue

                reddit_url = post.get("url", "")
                external_url = post.get("external_url", "")
                thumbnail = post.get("thumbnail")

                valid_links = set()
                source_links = set()

                if is_safe_link(external_url):
                    valid_links.add(external_url)

                if is_safe_link(reddit_url):
                    source_links.add(reddit_url)

                if valid_links:
                    # Search for IDs in both post text and the links themselves
                    search_blob = text + " " + " ".join(valid_links)
                    steam_ids = extract_steam_ids(search_blob)
                    epic_slugs = extract_epic_slugs(search_blob)
                    itch_urls = extract_itch_urls(search_blob)
                    ps_urls = extract_ps_urls(search_blob)
                    gog_urls = extract_gog_urls(search_blob)

                    parsed = {
                        "uri": uri,
                        "text": text,
                        "type": content_type,
                        "links": list(valid_links),
                        "source_links": list(source_links),
                        "steam_app_ids": list(steam_ids),
                        "epic_slugs": list(epic_slugs),
                        "itch_urls": list(itch_urls),
                        "ps_urls": list(ps_urls),
                        "gog_urls": list(gog_urls),
                        "image": thumbnail,
                    }

                    new_announcements.append((uri, parsed))
                    # We mark it as seen immediately to avoid processing it again
                    # In a more robust system, we might wait until confirmed transmission
                    if not ignore_seen:
                        await self.store.mark_post_seen(uri)

            return new_announcements

        except Exception as e:
            logger.exception("Error during sector scan: %s", e)
            return []
