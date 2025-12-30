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
            "thumbnail": "http://thumb.com/portal.jpg"
        },
        {
            "id": "post2",
            "title": "Discussion Thread",
            "url": "https://reddit.com/r/freegamefindings/post2",
            "external_url": "https://reddit.com/r/freegamefindings/post2", # Same as url (no external)
            "thumbnail": None
        }
    ]

    scanner = SectorScanner(mock_fetcher, mock_store)
    results = await scanner.scan()

    assert len(results) == 2
    
    # Check first result (Game)
    uri1, parsed1 = results[0]
    assert uri1 == "post1"
    assert parsed1["text"] == "Free Game: Portal"
    assert "https://store.steampowered.com/app/400/Portal" in parsed1["links"]
    assert "400" in parsed1["steam_app_ids"]
    assert parsed1["image"] == "http://thumb.com/portal.jpg"

    # Check second result (Discussion)
    uri2, parsed2 = results[1]
    assert uri2 == "post2"
    assert parsed2["text"] == "Discussion Thread"
    # When no external link is found, we fall back to the Reddit URL
    # This ensures the post is not ignored (since valid_links must be non-empty)
    assert "https://reddit.com/r/freegamefindings/post2" in parsed2["links"]
    assert "https://reddit.com/r/freegamefindings/post2" in parsed2["source_links"]

    # Verify store interaction
    assert mock_store.is_post_seen.call_count == 2
    assert mock_store.mark_post_seen.call_count == 2

@pytest.mark.asyncio
async def test_sector_scanner_skip_seen():
    mock_fetcher = MagicMock()
    mock_fetcher.fetch_latest = AsyncMock(return_value=[{"id": "seen_post"}])
    
    mock_store = MagicMock()
    mock_store.is_post_seen = AsyncMock(return_value=True) # It is seen
    mock_store.mark_post_seen = AsyncMock()

    scanner = SectorScanner(mock_fetcher, mock_store)
    results = await scanner.scan()

    assert len(results) == 0
    mock_store.mark_post_seen.assert_not_called()
