import os

import pytest

from bounty_core.epic import get_game_details as get_epic_details
from bounty_core.epic_api_manager import EpicAPIManager
from bounty_core.fetcher import RedditRSSFetcher
from bounty_core.itad_api_manager import ItadAPIManager
from bounty_core.itch import get_game_details as get_itch_details
from bounty_core.itch_api_manager import ItchAPIManager
from bounty_core.steam import get_game_details as get_steam_details
from bounty_core.steam_api_manager import SteamAPIManager


@pytest.mark.asyncio
async def test_steam_integration(session, store):
    """Test fetching details for Portal (App ID 400)."""
    manager = SteamAPIManager(session)
    details = await get_steam_details("400", manager, store)

    assert details is not None
    assert details["name"] == "Portal"
    assert details["store_url"] == "https://store.steampowered.com/app/400/"


@pytest.mark.asyncio
async def test_epic_integration(session, store):
    """Test fetching details for Fortnite."""
    manager = EpicAPIManager(session)
    details = await get_epic_details("fortnite", manager, store)

    assert details is not None
    assert "Fortnite" in details["name"]


@pytest.mark.asyncio
async def test_itch_integration(session, store):
    """Test scraping an itch.io page."""
    manager = ItchAPIManager(session)
    # Using a known game URL
    url = "https://tobyfox.itch.io/deltarune"
    details = await get_itch_details(url, manager, store)

    if details:
        assert details["name"] is not None
        assert "DELTARUNE" in details["name"]
        assert "itch.io" in details["publishers"]
    else:
        pytest.skip("Itch.io request failed or page layout changed")


@pytest.mark.asyncio
async def test_itad_integration(session):
    """Test ITAD API if key is present."""
    api_key = os.getenv("ITAD_API_KEY")
    if not api_key:
        pytest.skip("ITAD_API_KEY not set")

    manager = ItadAPIManager(session, api_key)
    # Search for a known game
    results = await manager.search_game("Portal")
    assert results
    assert any(g["title"] == "Portal" for g in results)

    # Check price
    best = await manager.get_best_price("Portal")
    assert best is not None
    assert "game_info" in best
    assert "price_info" in best


@pytest.mark.asyncio
async def test_scraper_feed(session):
    """Test fetching and parsing the Reddit RSS feed."""
    fetcher = RedditRSSFetcher(session)
    posts = await fetcher.fetch_latest(limit=5)

    assert isinstance(posts, list)
    # Note: Feed might be empty depending on the actor/filter

    if posts:
        post = posts[0]
        assert "id" in post
        assert "title" in post
        assert "url" in post
