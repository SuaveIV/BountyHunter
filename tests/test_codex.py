from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bounty_discord.cogs.codex import GalacticCodex


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.itad_manager = MagicMock()
    return bot


@pytest.fixture
def codex(mock_bot):
    return GalacticCodex(mock_bot)


@pytest.mark.asyncio
async def test_price_exact_match(codex, mock_bot):
    ctx = MagicMock()
    ctx.send = AsyncMock()

    # Setup mocks
    # search_game returns a list of games
    mock_bot.itad_manager.search_game = AsyncMock(
        return_value=[{"id": "game1", "title": "Portal 2"}, {"id": "game2", "title": "Portal"}]
    )

    # get_game_overview returns price info
    mock_bot.itad_manager.get_game_overview = AsyncMock(
        return_value={
            "prices": [
                {
                    "id": "game2",
                    "current": {
                        "price": {"amount": 5, "currency": "USD"},
                        "shop": {"name": "Steam"},
                        "url": "http://steam",
                    },
                    "lowest": {
                        "price": {"amount": 1, "currency": "USD"},
                        "shop": {"name": "Steam"},
                        "timestamp": "2020",
                    },
                    "urls": {"game": "http://itad/portal"},
                }
            ]
        }
    )

    # We need to patch ITAD_API_KEY to be truthy
    with patch("bounty_discord.cogs.codex.ITAD_API_KEY", "test_key"):
        await codex.check_price.callback(codex, ctx, title="Portal")

    # Verify search was called
    mock_bot.itad_manager.search_game.assert_called_with("Portal", limit=5)

    # Verify exact match was picked ("Portal" vs "Portal 2")
    # "Portal" matches exactly.
    mock_bot.itad_manager.get_game_overview.assert_called_with(["game2"])

    # Verify embed sent
    # We expect 2 calls: one "Checking price...", one with embed
    assert ctx.send.call_count == 2
    args, kwargs = ctx.send.call_args
    embed = kwargs.get("embed")
    if not embed and args:
        # If embed passed as positional argument (unlikely for ctx.send but possible if mocked differently)
        # discord.py send signature: send(content=None, *, tts=False, embed=None, ...)
        # So usually embed is kwarg.
        pass

    # The last call should have an embed
    assert embed is not None
    assert embed.title == "Portal"


@pytest.mark.asyncio
async def test_price_fuzzy_match(codex, mock_bot):
    ctx = MagicMock()
    ctx.send = AsyncMock()

    # Search returns only "Portal 2" when searching for "Portal"
    mock_bot.itad_manager.search_game = AsyncMock(return_value=[{"id": "game1", "title": "Portal 2"}])

    mock_bot.itad_manager.get_game_overview = AsyncMock(
        return_value={"prices": [{"id": "game1", "current": None, "lowest": None, "urls": {"game": "http"}}]}
    )

    with patch("bounty_discord.cogs.codex.ITAD_API_KEY", "test_key"):
        await codex.check_price.callback(codex, ctx, title="Portal")

    # Should warn about exact match not found
    # We expect 3 calls: "Checking...", "Warning: Exact match not found...", "Embed"
    assert ctx.send.call_count == 3

    # Verify warning message
    calls = ctx.send.call_args_list
    warning_call = calls[1]
    assert "Exact match not found" in warning_call[0][0]
    assert "Portal 2" in warning_call[0][0]


@pytest.mark.asyncio
async def test_price_not_found(codex, mock_bot):
    ctx = MagicMock()
    ctx.send = AsyncMock()

    mock_bot.itad_manager.search_game = AsyncMock(return_value=[])

    with patch("bounty_discord.cogs.codex.ITAD_API_KEY", "test_key"):
        await codex.check_price.callback(codex, ctx, title="Ghost Game")

    # Should say "not found"
    assert ctx.send.call_count == 2  # Checking + Error
    assert "not found" in ctx.send.call_args[0][0]
