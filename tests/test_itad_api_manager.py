from unittest.mock import AsyncMock, MagicMock

import pytest

from bounty_core.itad_api_manager import ItadAPIManager

VHS_TROLL_GAME = "FIRST STEAM GAME VHS - COLOR RETRO RACER : MILES CHALLENGE"


def make_manager(results: list[dict]) -> ItadAPIManager:
    manager = ItadAPIManager(session=MagicMock(), api_key="test-key")
    manager.search_game = AsyncMock(return_value=results)
    manager.lookup_game = AsyncMock(return_value=None)
    return manager


@pytest.mark.asyncio
async def test_find_game_trusts_exact_steam_lookups():
    manager = make_manager([])
    manager.lookup_game = AsyncMock(return_value={"title": "Portal", "assets": {}})

    details = await manager.find_game(steam_ids=["400"], title="something entirely unrelated")

    assert details is not None
    assert details["name"] == "Portal"
    manager.search_game.assert_not_called()


@pytest.mark.asyncio
async def test_find_game_rejects_unrelated_fuzzy_matches():
    """ITAD answers a bad query with its best guess; a failed lookup must stay a failure."""
    manager = make_manager([{"title": VHS_TROLL_GAME, "assets": {}}])

    assert await manager.find_game(title="Exiled Giveaways and Itch.io Mega Threads") is None
    assert await manager.find_game(title="Blair Witch") is None
    # The Epic slug path searches by title too, so it is validated the same way.
    assert await manager.find_game(epic_slugs=["blair-witch"]) is None


@pytest.mark.asyncio
async def test_find_game_accepts_a_matching_candidate():
    manager = make_manager(
        [
            {"title": VHS_TROLL_GAME, "assets": {}},
            {"title": "Blair Witch", "assets": {"boxart": "https://img.example/blair.jpg"}},
        ]
    )

    details = await manager.find_game(title="Blair Witch")

    assert details is not None
    assert details["name"] == "Blair Witch"
    assert details["image"] == "https://img.example/blair.jpg"
    assert details["price_info"] == "Free to Play"
    # More than one candidate is inspected before giving up on the lookup.
    assert manager.search_game.await_args.kwargs["limit"] > 1


@pytest.mark.asyncio
async def test_find_game_returns_none_without_ids_or_title():
    manager = make_manager([])

    assert await manager.find_game() is None
    assert await manager.find_game(title="") is None


@pytest.mark.asyncio
async def test_get_best_price_refuses_an_unrelated_match():
    """`!price <garbage>` should report nothing rather than another game's price."""
    manager = make_manager([{"id": "1", "title": VHS_TROLL_GAME}])
    manager.get_game_overview = AsyncMock(return_value={"prices": [{"id": "1", "current": {"amount": 0}}]})

    assert await manager.get_best_price("asdkjhasd") is None
    manager.get_game_overview.assert_not_called()


@pytest.mark.asyncio
async def test_get_best_price_accepts_a_matching_game():
    manager = make_manager([{"id": "1", "title": "Portal"}])
    manager.get_game_overview = AsyncMock(return_value={"prices": [{"id": "1", "current": {"amount": 9.99}}]})

    best = await manager.get_best_price("Portal")

    assert best is not None
    assert best["game_info"]["title"] == "Portal"
