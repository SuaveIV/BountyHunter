from unittest.mock import AsyncMock, MagicMock

import pytest

from bounty_discord.utils import (
    create_game_embed,
    enhance_details_with_itad,
    get_fallback_details,
)


@pytest.mark.asyncio
async def test_create_game_embed_steam():
    details = {
        "name": "Test Game",
        "store_url": "https://store.steampowered.com/app/123",
        "short_description": "A cool game",
        "image": "http://img.com/123",
        "price_info": {"original_price": "$10", "discount_percent": 100},
    }
    parsed = {"type": "GAME"}

    embed = await create_game_embed(details, parsed)

    assert embed.title == "FREE GAME: Test Game"
    assert embed.url == details["store_url"]
    assert embed.color and embed.color.value == 65280  # Green #00FF00
    assert embed.description == "A cool game"
    assert embed.image.url == "http://img.com/123"

    # Check fields
    fields = {f.name: f.value for f in embed.fields}
    assert "Price" in fields
    assert "~~$10~~ -> FREE (100% off)" in str(fields["Price"])


@pytest.mark.asyncio
async def test_create_game_embed_epic():
    details = {
        "name": "Epic Game",
        "store_url": "https://store.epicgames.com/p/game",
        "image": "http://img.com/epic",
    }
    parsed = {"type": "GAME"}

    embed = await create_game_embed(details, parsed)

    assert embed.color and embed.color.value == 30962  # Epic Blue #0078F2
    assert "Epic Games Store" in [f.value for f in embed.fields if f.name == "Platform"]


@pytest.mark.asyncio
async def test_get_fallback_details_basic():
    links = ["https://store.steampowered.com/app/123"]
    text = "Free Game: My Game"
    manager = MagicMock()

    details = await get_fallback_details(links, text, manager)

    assert details["name"] == "Free Game: My Game"
    assert details["store_url"] == links[0]
    assert details["image"] is None


@pytest.mark.asyncio
async def test_enhance_details_with_itad_success():
    details = {"name": "Portal", "image": None}

    mock_manager = MagicMock()
    mock_manager.api_key = "test_key"
    mock_manager.search_game = AsyncMock(
        return_value=[{"title": "Portal", "assets": {"banner400": "http://img.com/portal.jpg"}}]
    )

    await enhance_details_with_itad(details, mock_manager)

    assert details["image"] == "http://img.com/portal.jpg"
    mock_manager.search_game.assert_called_once_with("Portal", limit=1)


@pytest.mark.asyncio
async def test_enhance_details_with_itad_no_result():
    details = {"name": "Unknown Game", "image": None}
    mock_manager = MagicMock()
    mock_manager.api_key = "test_key"
    mock_manager.search_game = AsyncMock(return_value=[])

    await enhance_details_with_itad(details, mock_manager)

    assert details["image"] is None
