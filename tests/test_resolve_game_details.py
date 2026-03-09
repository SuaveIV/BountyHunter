from unittest.mock import AsyncMock, MagicMock

import pytest

from bounty_discord.utils import resolve_game_details, select_best_game_details


class TestSelectBestGameDetails:
    """Test the select_best_game_details function."""

    def test_empty_results_returns_none(self):
        """Test that empty results list returns None."""
        result = select_best_game_details([])
        assert result is None

    def test_image_priority(self):
        """Test that image has the highest priority."""
        results = [
            {"name": "Game A", "image": "url1", "short_description": None},
            {"name": "Game B", "image": None, "short_description": "desc"},
        ]
        best = select_best_game_details(results)
        assert best is not None
        assert best["name"] == "Game A"

    def test_description_vs_price_info(self):
        """Test that description has higher priority than price info."""
        results = [
            {"name": "Game A", "image": None, "short_description": "desc", "price_info": None},
            {"name": "Game B", "image": None, "short_description": None, "price_info": "free"},
        ]
        best = select_best_game_details(results)
        assert best is not None
        assert best["name"] == "Game A"

    def test_developer_publisher_priority(self):
        """Test that developer/publisher info has higher priority than release date."""
        results = [
            {"name": "Game A", "image": None, "developers": ["Dev"], "release_date": "2020-01-01"},
            {"name": "Game B", "image": None, "developers": [], "release_date": "2020-01-01"},
        ]
        best = select_best_game_details(results)
        assert best is not None
        assert best["name"] == "Game A"

    def test_name_quality_penalty(self):
        """Test that 'Free Game' name is penalized."""
        results = [
            {"name": "Portal 2", "image": "url1", "short_description": "desc"},
            {"name": "Free Game", "image": "url2", "short_description": "desc"},
        ]
        best = select_best_game_details(results)
        assert best is not None
        assert best["name"] == "Portal 2"

    def test_complete_data_wins(self):
        """Test that the most complete result wins."""
        results = [
            {"name": "Game A", "image": "url1", "short_description": "desc", "price_info": "free"},
            {
                "name": "Game B",
                "image": "url2",
                "short_description": "desc",
                "price_info": "free",
                "developers": ["Dev"],
            },
        ]
        best = select_best_game_details(results)
        assert best is not None
        assert best["name"] == "Game B"


class TestResolveGameDetails:
    """Test the refactored resolve_game_details function."""

    @pytest.mark.asyncio
    async def test_cross_platform_giveaway_selects_best_result(self):
        """Test that cross-platform giveaways try all stores and select the best result."""
        # Mock bot with managers
        mock_bot = MagicMock()
        mock_bot.steam_manager = AsyncMock()
        mock_bot.epic_manager = AsyncMock()
        mock_bot.store = MagicMock()

        # Mock parsed data with both Steam and Epic links
        parsed_data = {
            "steam_app_ids": ["12345"],
            "epic_slugs": ["portal-2"],
            "links": ["https://store.steampowered.com/app/12345/", "https://store.epicgames.com/p/portal-2"],
            "text": "[Steam] (Game) Portal 2 is free",
            "type": "GAME",
        }

        # Mock Steam result (has image but no description)
        steam_result = {
            "name": "Portal 2",
            "image": "https://steamcdn.com/portal2.jpg",
            "price_info": "Free to Play",
            "developers": ["Valve"],
            "publishers": ["Valve"],
            "release_date": "2011-04-19",
            # No short_description
        }

        # Mock Epic result (has description but no image)
        epic_result = {
            "name": "Portal 2",
            "short_description": "A mind-bending puzzle adventure from Valve",
            "price_info": "Free",
            "developers": ["Valve"],
            "publishers": ["Valve"],
            "release_date": "2011-04-19",
            # No image
        }

        # Mock the get_steam_details and get_epic_details functions
        async def mock_get_steam_details(appid, manager, store):
            return steam_result

        async def mock_get_epic_details(slug, manager, store):
            return epic_result

        # Patch the functions
        import bounty_discord.utils as utils

        original_steam = utils.get_steam_details
        original_epic = utils.get_epic_details

        utils.get_steam_details = mock_get_steam_details
        utils.get_epic_details = mock_get_epic_details

        try:
            # Test the refactored function
            result = await resolve_game_details(mock_bot, parsed_data)

            # The result should be the Steam result because it has an image (100 points)
            # while Epic only has a description (50 points)
            assert result == steam_result
        finally:
            # Restore original functions
            utils.get_steam_details = original_steam
            utils.get_epic_details = original_epic

    @pytest.mark.asyncio
    async def test_all_stores_fail_returns_none(self):
        """Test that when all stores fail, the function returns None."""
        # Mock bot with managers
        mock_bot = MagicMock()
        mock_bot.steam_manager = AsyncMock()
        mock_bot.epic_manager = AsyncMock()
        mock_bot.store = MagicMock()
        mock_bot.itad_manager = None  # No ITAD manager to prevent fallback

        # Mock parsed data
        parsed_data = {
            "steam_app_ids": ["12345"],
            "epic_slugs": ["portal-2"],
            "links": ["https://store.steampowered.com/app/12345/"],
            "text": "[Steam] (Game) Portal 2 is free",
            "type": "GAME",
        }

        # Mock functions that return None
        async def mock_get_nothing(appid, manager, store):
            return None

        # Mock fallback function to return None
        async def mock_get_fallback_details(links, text, itad_manager, image=None):
            return None

        # Patch the functions
        import bounty_discord.utils as utils

        original_steam = utils.get_steam_details
        original_epic = utils.get_epic_details
        original_fallback = utils.get_fallback_details

        utils.get_steam_details = mock_get_nothing
        utils.get_epic_details = mock_get_nothing
        utils.get_fallback_details = mock_get_fallback_details

        try:
            result = await resolve_game_details(mock_bot, parsed_data)
            assert result is None
        finally:
            # Restore original functions
            utils.get_steam_details = original_steam
            utils.get_epic_details = original_epic
            utils.get_fallback_details = original_fallback

    @pytest.mark.asyncio
    async def test_access_denied_continues_with_other_stores(self):
        """Test that AccessDenied errors don't stop processing other stores."""
        # Mock bot with managers
        mock_bot = MagicMock()
        mock_bot.steam_manager = AsyncMock()
        mock_bot.epic_manager = AsyncMock()
        mock_bot.store = MagicMock()

        # Mock parsed data
        parsed_data = {
            "steam_app_ids": ["12345"],
            "epic_slugs": ["portal-2"],
            "links": ["https://store.steampowered.com/app/12345/"],
            "text": "[Steam] (Game) Portal 2 is free",
            "type": "GAME",
        }

        # Mock Steam result that raises AccessDenied
        async def mock_get_steam_details_access_denied(appid, manager, store):
            from bounty_core.exceptions import AccessDenied

            raise AccessDenied("Steam", 403)

        # Mock Epic result that succeeds
        epic_result = {
            "name": "Portal 2",
            "short_description": "A mind-bending puzzle adventure from Valve",
            "price_info": "Free",
            "developers": ["Valve"],
            "publishers": ["Valve"],
            "release_date": "2011-04-19",
        }

        async def mock_get_epic_details_success(slug, manager, store):
            return epic_result

        # Patch the functions
        import bounty_discord.utils as utils

        original_steam = utils.get_steam_details
        original_epic = utils.get_epic_details

        utils.get_steam_details = mock_get_steam_details_access_denied
        utils.get_epic_details = mock_get_epic_details_success

        try:
            result = await resolve_game_details(mock_bot, parsed_data)
            # Should return the Epic result despite Steam failing
            assert result == epic_result
        finally:
            # Restore original functions
            utils.get_steam_details = original_steam
            utils.get_epic_details = original_epic

    @pytest.mark.asyncio
    async def test_single_store_success(self):
        """Test that single store success still works as before."""
        # Mock bot with managers
        mock_bot = MagicMock()
        mock_bot.steam_manager = AsyncMock()
        mock_bot.store = MagicMock()

        # Mock parsed data with only Steam
        parsed_data = {
            "steam_app_ids": ["12345"],
            "links": ["https://store.steampowered.com/app/12345/"],
            "text": "[Steam] (Game) Portal 2 is free",
            "type": "GAME",
        }

        # Mock Steam result
        steam_result = {
            "name": "Portal 2",
            "image": "https://steamcdn.com/portal2.jpg",
            "short_description": "A mind-bending puzzle adventure from Valve",
            "price_info": "Free to Play",
            "developers": ["Valve"],
            "publishers": ["Valve"],
            "release_date": "2011-04-19",
        }

        async def mock_get_steam_details(appid, manager, store):
            return steam_result

        # Patch the function
        import bounty_discord.utils as utils

        original_steam = utils.get_steam_details

        utils.get_steam_details = mock_get_steam_details

        try:
            result = await resolve_game_details(mock_bot, parsed_data)
            assert result == steam_result
        finally:
            # Restore original function
            utils.get_steam_details = original_steam
