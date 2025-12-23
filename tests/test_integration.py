import pytest

from bounty_core.epic import get_game_details as get_epic_details
from bounty_core.epic_api_manager import EpicAPIManager
from bounty_core.fetcher import BlueskyFetcher
from bounty_core.itch import get_game_details as get_itch_details
from bounty_core.itch_api_manager import ItchAPIManager
from bounty_core.parser import extract_links
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
    # Using a known game URL (Vimlark is a consistent dev)
    url = "https://vimlark.itch.io/ynglet"
    details = await get_itch_details(url, manager, store)

    if details:
        assert details["name"] is not None
        assert "itch.io" in details["publishers"]
    else:
        pytest.skip("Itch.io request failed or page layout changed")


@pytest.mark.asyncio
async def test_scraper_feed(session):
    """Test fetching and parsing the Bluesky feed."""
    fetcher = BlueskyFetcher(session)
    posts = await fetcher.fetch_latest()

    assert isinstance(posts, list)
    # Note: Feed might be empty depending on the actor/filter

    if posts:
        post = posts[0]
        assert "uri" in post
        assert "record" in post

        # Verify parser works on real data
        links = extract_links(post)
        assert isinstance(links, set)
