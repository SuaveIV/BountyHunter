"""
SectorScanner: the fan-in between the free-game fetchers and the Discord layer.

Every fetcher in :mod:`bounty_core.fetcher` is an independent source, so one failing feed
only degrades a scan instead of failing it. Listings are filtered, deduplicated across
sources, and then translated into the flat "parsed" dict that
:class:`~bounty_discord.cogs.visor.SectorVisor` and the embed helpers already understand.
"""

import logging
from typing import Any

import aiohttp

from bounty_core.fetcher import (
    CONTENT_BETA,
    CONTENT_DLC,
    CONTENT_GAME,
    CONTENT_ITEM,
    FreeGame,
    FreeGamesFetcher,
    dedupe_games,
    default_free_games_fetchers,
    fetch_all_games,
    filter_games,
)
from bounty_core.parser import (
    URL_REGEX,
    extract_epic_slugs,
    extract_gog_urls,
    extract_itch_urls,
    extract_ps_urls,
    extract_steam_ids,
)
from bounty_core.store import Store

logger = logging.getLogger(__name__)

#: Maps the normalized content type onto the legacy parsed "type" the embeds render.
CONTENT_POST_TYPES = {
    CONTENT_GAME: "GAME",
    CONTENT_DLC: "ITEM",
    CONTENT_ITEM: "ITEM",
    CONTENT_BETA: "ITEM",
}

EPIC_MOBILE_MARKERS = (("-android-", "Android"), ("-ios-", "iOS"))
LINK_TRAILING_CHARS = ").,;:"


def _listing_links(game: FreeGame) -> list[str]:
    """
    Collect the listing URL plus any store links embedded in the body text.

    Bluesky listings point at a Reddit thread, so the body link (when there is one) is
    what lets the store managers resolve a rich embed.
    """
    links: list[str] = []

    def add(url: str) -> None:
        cleaned = url.rstrip(LINK_TRAILING_CHARS).strip()
        if cleaned and cleaned not in links:
            links.append(cleaned)

    if game.url:
        add(game.url)

    for match in URL_REGEX.findall(game.text or ""):
        add(match)

    return links


def _epic_mobile_links(links: list[str]) -> dict[str, str]:
    """Flag Epic Android/iOS variants so the embed can call them out."""
    mobile: dict[str, str] = {}
    for link in links:
        if "store.epicgames.com" not in link:
            continue
        lowered = link.lower()
        for marker, label in EPIC_MOBILE_MARKERS:
            if marker in lowered:
                mobile.setdefault(label, link)
    return mobile


def _listing_text(game: FreeGame) -> str:
    """
    Title plus body, without printing the title twice.

    Epic and GamerPower put the title at the start of their text, and a Bluesky post repeats
    it inside its own opening line, so the title only gets prepended when the body does not
    already open with it.
    """
    body = (game.text or "").strip()
    if not body:
        return game.title

    first_line = body.splitlines()[0]
    if game.title.lower() in first_line.lower():
        return body

    return f"{game.title}\n{body}"


def parsed_from_free_game(game: FreeGame) -> dict[str, Any]:
    """Translate a normalized :class:`FreeGame` into the parsed dict the visor renders."""
    links = _listing_links(game)
    blob = " ".join([game.title, game.text or "", *links])

    return {
        "uri": game.dedupe_key,
        "title": game.title,
        "text": _listing_text(game),
        "source": game.source,
        "source_id": game.source_id,
        "content_type": game.content_type,
        "type": CONTENT_POST_TYPES.get(game.content_type, "UNKNOWN"),
        "platforms": sorted(game.platforms),
        "expires_at": game.expires_at,
        "links": links,
        "source_links": [],
        "steam_app_ids": sorted(extract_steam_ids(blob)),
        "epic_slugs": sorted(extract_epic_slugs(blob)),
        "epic_mobile_links": _epic_mobile_links(links),
        "itch_urls": sorted(extract_itch_urls(blob)),
        "ps_urls": sorted(extract_ps_urls(blob)),
        "gog_urls": sorted(extract_gog_urls(blob)),
        "image": None,
    }


class SectorScanner:
    """Scans every free-game source for new bounties (free games)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        store: Store,
        fetchers: list[FreeGamesFetcher] | None = None,
    ):
        self.session = session
        self.store = store
        self.fetchers = fetchers if fetchers is not None else default_free_games_fetchers(session)

    async def scan(self, ignore_seen: bool = False) -> list[tuple[str, dict[str, Any]]]:
        """
        Scans the configured sources for new deals.

        Returns a list of ``(dedupe_key, parsed_data)`` tuples for new, unseen listings.
        If ignore_seen is True, returns all fetched listings (useful for testing).

        The first run on a fresh database seeds every accepted listing as seen instead of
        announcing it, so a new install does not dump the entire active backlog into the
        channel. Valid posts are otherwise marked seen by SectorVisor._announce_new after
        announcement is attempted, so a crash or send failure retries rather than silently
        losing the post.
        """
        try:
            games = await fetch_all_games(self.fetchers)
            accepted = dedupe_games(filter_games(games))

            if not accepted:
                return []

            seeding = not ignore_seen and not await self.store.has_seen_posts()
            announcements: list[tuple[str, dict[str, Any]]] = []

            for game in accepted:
                key = game.dedupe_key

                if seeding:
                    await self.store.mark_post_seen(key)
                    continue

                if not ignore_seen and await self.store.is_post_seen(key):
                    continue

                announcements.append((key, parsed_from_free_game(game)))

            if seeding:
                logger.info(f"First run: seeded {len(accepted)} listing(s) as already seen")

            return announcements

        except Exception as e:
            logger.exception("Error during sector scan: %s", e)
            return []
