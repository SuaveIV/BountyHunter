from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bounty_discord.gunship import Gunship


@pytest.mark.asyncio
async def test_gunship_initialization():
    # Mock aiohttp.ClientSession because it is created in __init__
    with patch("aiohttp.ClientSession", return_value=MagicMock()) as mock_session:
        # Mock managers to avoid real API calls or errors
        with (
            patch("bounty_discord.gunship.SteamAPIManager"),
            patch("bounty_discord.gunship.EpicAPIManager"),
            patch("bounty_discord.gunship.ItchAPIManager"),
            patch("bounty_discord.gunship.PSAPIManager"),
            patch("bounty_discord.gunship.GogAPIManager"),
            patch("bounty_discord.gunship.ItadAPIManager"),
            patch("bounty_discord.gunship.SectorScanner"),
            patch("bounty_discord.gunship.Store"),
            patch("bounty_discord.gunship.Database"),
        ):
            intents = discord.Intents.default()
            bot = Gunship(command_prefix="!", intents=intents)

            assert isinstance(bot, commands.Bot)
            assert bot.steam_manager is not None
            assert bot.epic_manager is not None
            assert bot.scanner is not None
            assert bot.store is not None

            # Check session creation
            mock_session.assert_called_once()


@pytest.mark.asyncio
async def test_gunship_setup_hook():
    with patch("aiohttp.ClientSession", return_value=MagicMock()):
        with (
            patch("bounty_discord.gunship.SteamAPIManager"),
            patch("bounty_discord.gunship.EpicAPIManager"),
            patch("bounty_discord.gunship.ItchAPIManager"),
            patch("bounty_discord.gunship.PSAPIManager"),
            patch("bounty_discord.gunship.GogAPIManager"),
            patch("bounty_discord.gunship.ItadAPIManager"),
            patch("bounty_discord.gunship.SectorScanner"),
            patch("bounty_discord.gunship.Store") as MockStore,
            patch("bounty_discord.gunship.Database"),
        ):
            # Configure Store mock to support await setup()
            mock_store_instance = MockStore.return_value
            mock_store_instance.setup = AsyncMock()

            bot = Gunship(command_prefix="!", intents=discord.Intents.default())

            # Mock load_extension to verify it's called
            bot.load_extension = AsyncMock()

            # Mock logging handler setup
            with patch("logging.getLogger"):
                await bot.setup_hook()

            # Verify store setup was called
            mock_store_instance.setup.assert_awaited_once()

            # Verify extensions are loaded
            expected_extensions = [
                "bounty_discord.cogs.visor",
                "bounty_discord.cogs.admin",
                "bounty_discord.cogs.codex",
                "bounty_discord.cogs.beacons",
            ]

            for ext in expected_extensions:
                bot.load_extension.assert_any_call(ext)
