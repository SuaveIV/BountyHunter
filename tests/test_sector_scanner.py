from unittest.mock import AsyncMock, MagicMock

import pytest

from bounty_discord.modules.sector_scanner import SectorScanner


@pytest.mark.asyncio
async def test_sector_scanner_scan():
    # Mock dependencies
    mock_fetcher = MagicMock()
    mock_fetcher.fetch_latest = AsyncMock()

    mock_store = MagicMock()
    mock_store.is_post_seen = AsyncMock(return_value=False)
    mock_store.mark_post_seen = AsyncMock()

    # Mock data returned by fetcher
    mock_fetcher.fetch_latest.return_value = [
        {
            "id": "post1",
            "title": "Free Game: Portal",
            "url": "https://reddit.com/r/freegamefindings/post1",
            "external_url": "https://store.steampowered.com/app/400/Portal",
            "thumbnail": "http://thumb.com/portal.jpg",
        },
        {
            "id": "post2",
            "title": "Epic Game: Fortnite",
            "url": "https://reddit.com/r/freegamefindings/post2",
            "external_url": "https://store.epicgames.com/p/fortnite",
            "thumbnail": None,
        },
        {
            "id": "post3",
            "title": "Itch Game",
            "url": "https://reddit.com/r/freegamefindings/post3",
            "external_url": "https://mygame.itch.io/cool-game",
            "thumbnail": None,
        },
        {
            "id": "post4",
            "title": "Bad Link",
            "url": "https://reddit.com/r/freegamefindings/post4",
            "external_url": "https://gleam.io/reward",
            "thumbnail": None,
        },
        {
            "id": "post5",
            "title": "Discussion Thread",
            "url": "https://reddit.com/r/freegamefindings/post5",
            "external_url": "https://reddit.com/r/freegamefindings/post5",  # Same as url (no external)
            "thumbnail": None,
        },
    ]

    scanner = SectorScanner(mock_fetcher, mock_store)
    results = await scanner.scan()

    # Post 4 should be skipped because gleam.io is in DENY_DOMAINS
    # So we expect 4 results
    assert len(results) == 4

    # Check first result (Steam)
    uri1, parsed1 = results[0]
    assert uri1 == "post1"
    assert "https://store.steampowered.com/app/400/Portal" in parsed1["links"]
    assert "400" in parsed1["steam_app_ids"]

    # Check second result (Epic)
    uri2, parsed2 = results[1]
    assert uri2 == "post2"
    assert "https://store.epicgames.com/p/fortnite" in parsed2["links"]
    assert "fortnite" in parsed2["epic_slugs"]

    # Check third result (Itch)
    uri3, parsed3 = results[2]
    assert uri3 == "post3"
    assert "https://mygame.itch.io/cool-game" in parsed3["links"]
    assert "https://mygame.itch.io/cool-game" in parsed3["itch_urls"]

    # Check fourth result (Discussion - post5)
    uri5, parsed5 = results[3]
    assert uri5 == "post5"
    assert "https://reddit.com/r/freegamefindings/post5" in parsed5["links"]

    # Verify store interaction
    # is_post_seen called for all 5 posts
    assert mock_store.is_post_seen.call_count == 5
    # mark_post_seen called only for the 4 valid posts
    assert mock_store.mark_post_seen.call_count == 4


@pytest.mark.asyncio
async def test_sector_scanner_skip_seen():
    mock_fetcher = MagicMock()
    mock_fetcher.fetch_latest = AsyncMock(return_value=[{"id": "seen_post"}])

    mock_store = MagicMock()
    mock_store.is_post_seen = AsyncMock(return_value=True)  # It is seen
    mock_store.mark_post_seen = AsyncMock()

    scanner = SectorScanner(mock_fetcher, mock_store)
    results = await scanner.scan()

    assert len(results) == 0
    mock_store.mark_post_seen.assert_not_called()
