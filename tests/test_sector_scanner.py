from unittest.mock import AsyncMock

import pytest

from bounty_core.fetcher import FreeGame
from bounty_discord.modules.sector_scanner import SectorScanner, parsed_from_free_game


class StubFetcher:
    """Stand-in for a bounty_core.fetcher source adapter."""

    name = "stub"

    def __init__(self, games: list[FreeGame] | None = None, error: Exception | None = None):
        self.games = games or []
        self.error = error
        self.calls = 0

    async def fetch_games(self) -> list[FreeGame]:
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.games)


def make_game(**kwargs) -> FreeGame:
    defaults = {
        "source": "epic",
        "source_id": "1",
        "title": "Portal",
        "url": "https://store.epicgames.com/en-US/p/portal",
        "platforms": {"epic"},
        "text": "Portal is free!",
    }
    defaults.update(kwargs)
    return FreeGame(**defaults)


def make_store(seen: bool = False, has_seen: bool = True):
    store = AsyncMock()
    store.is_post_seen = AsyncMock(return_value=seen)
    store.mark_post_seen = AsyncMock()
    store.has_seen_posts = AsyncMock(return_value=has_seen)
    return store


@pytest.mark.asyncio
async def test_scan_returns_new_listings():
    fetcher = StubFetcher(
        [
            make_game(source_id="1", title="Portal", url="https://store.steampowered.com/app/400/Portal"),
            make_game(source_id="2", title="Fortnite", url="https://store.epicgames.com/p/fortnite"),
        ]
    )
    store = make_store()
    scanner = SectorScanner(session=AsyncMock(), store=store, fetchers=[fetcher])

    results = await scanner.scan()

    assert [key for key, _ in results] == ["epic:1", "epic:2"]

    _, parsed = results[0]
    assert parsed["uri"] == "epic:1"
    assert parsed["source"] == "epic"
    assert parsed["title"] == "Portal"
    assert "400" in parsed["steam_app_ids"]
    assert "https://store.steampowered.com/app/400/Portal" in parsed["links"]
    assert parsed["type"] == "GAME"

    # Announcements are marked seen by the visor, not the scanner.
    store.mark_post_seen.assert_not_called()


@pytest.mark.asyncio
async def test_scan_filters_and_dedupes_across_sources():
    fetcher = StubFetcher(
        [
            make_game(source_id="1", title="BURIED STARS", url="https://store.epicgames.com/p/buried-stars"),
            # Same game, different source: dedupe keeps the first sighting (Epic).
            make_game(
                source="bluesky",
                source_id="at://post/2",
                title="BURIED STARS (Epic Games) Giveaway",
                url="https://redd.it/abc",
                platforms={"epic"},
            ),
            # Raffles are dropped by the excluded-keyword filter.
            make_game(source_id="3", title="Raffle time", text="raffle", platforms={"steam"}),
            # No storefront from the whitelist.
            make_game(source_id="4", title="Mobile only", platforms={"android"}),
        ]
    )
    scanner = SectorScanner(session=AsyncMock(), store=make_store(), fetchers=[fetcher])

    results = await scanner.scan()

    assert [key for key, _ in results] == ["epic:1"]


@pytest.mark.asyncio
async def test_scan_skips_seen_listings():
    fetcher = StubFetcher([make_game()])
    store = make_store(seen=True)
    scanner = SectorScanner(session=AsyncMock(), store=store, fetchers=[fetcher])

    assert await scanner.scan() == []


@pytest.mark.asyncio
async def test_scan_seeds_first_run_without_announcing():
    fetcher = StubFetcher([make_game(source_id="1"), make_game(source_id="2", title="Second")])
    store = make_store(has_seen=False)
    scanner = SectorScanner(session=AsyncMock(), store=store, fetchers=[fetcher])

    assert await scanner.scan() == []
    assert store.mark_post_seen.await_count == 2
    store.mark_post_seen.assert_any_await("epic:1")
    store.mark_post_seen.assert_any_await("epic:2")

    # A later run announces nothing either, because both listings are now seen.
    store.is_post_seen = AsyncMock(return_value=True)
    store.has_seen_posts = AsyncMock(return_value=True)
    assert await scanner.scan() == []


@pytest.mark.asyncio
async def test_scan_survives_a_dead_source():
    good = StubFetcher([make_game()])
    bad = StubFetcher(error=RuntimeError("feed is down"))
    scanner = SectorScanner(session=AsyncMock(), store=make_store(), fetchers=[bad, good])

    results = await scanner.scan()

    assert [key for key, _ in results] == ["epic:1"]
    assert bad.calls == 1 and good.calls == 1


@pytest.mark.asyncio
async def test_scan_ignore_seen_bypasses_seeding_and_dedupe_store():
    fetcher = StubFetcher([make_game()])
    store = make_store(seen=True, has_seen=False)
    scanner = SectorScanner(session=AsyncMock(), store=store, fetchers=[fetcher])

    results = await scanner.scan(ignore_seen=True)

    assert len(results) == 1
    store.is_post_seen.assert_not_called()
    store.mark_post_seen.assert_not_called()


def test_parsed_from_free_game_collects_store_links_from_body():
    game = make_game(
        source="bluesky",
        source_id="at://post/1",
        title="Blair Witch is free!",
        url="https://redd.it/xyz",
        platforms={"steam"},
        text="[Steam] (Game) Blair Witch is free! https://store.steampowered.com/app/1094840/",
        content_type="dlc",
    )

    parsed = parsed_from_free_game(game)

    assert parsed["links"] == [
        "https://redd.it/xyz",
        "https://store.steampowered.com/app/1094840/",
    ]
    assert parsed["steam_app_ids"] == ["1094840"]
    assert parsed["content_type"] == "dlc"
    assert parsed["type"] == "ITEM"
    assert parsed["platforms"] == ["steam"]
