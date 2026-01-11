import logging
from typing import Any

import aiohttp

from bounty_core.exceptions import (
    AccessDenied,
    APIError,
    GameNotFound,
    NetworkError,
    RateLimitExceeded,
)
from bounty_core.network import HEADERS

logger = logging.getLogger(__name__)


class ItadAPIManager:
    """
    Manages interactions with the IsThereAnyDeal API (v1/v2).
    Used for price checking and metadata enhancement.
    """

    BASE_URL = "https://api.isthereanydeal.com"

    def __init__(self, session: aiohttp.ClientSession, api_key: str):
        self.session = session
        self.api_key = api_key

    async def search_game(self, title: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Search for games by title.
        """
        if not self.api_key:
            logger.warning("ITAD API Key not set. skipping search.")
            return []

        url = f"{self.BASE_URL}/games/search/v1"
        params = {"key": self.api_key, "title": title, "results": limit}
        try:
            async with self.session.get(url, params=params, headers=HEADERS) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                elif resp.status == 429:
                    raise RateLimitExceeded("ITAD")
                elif resp.status in (401, 403):
                    raise AccessDenied("ITAD", resp.status)
                else:
                    raise APIError("ITAD", resp.status, await resp.text())
        except aiohttp.ClientError as e:
            raise NetworkError(f"ITAD connection failed: {e}", e) from e
        except (RateLimitExceeded, AccessDenied, APIError):
            raise
        except Exception as e:
            logger.error(f"Error searching ITAD for {title}: {e}")
            raise APIError("ITAD", message=str(e)) from e

    async def lookup_game(self, shop: str, game_id: str) -> dict | None:
        """
        Lookup a game by shop ID (e.g. steam/400).
        """
        if not self.api_key:
            return None

        url = f"{self.BASE_URL}/games/lookup/v1"
        params = {"key": self.api_key, "shop": shop, "id": game_id}
        try:
            async with self.session.get(url, params=params, headers=HEADERS) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("found"):
                        return data.get("game")
                    raise GameNotFound(f"{shop}/{game_id}", "ITAD")
                elif resp.status == 429:
                    raise RateLimitExceeded("ITAD")
                elif resp.status in (401, 403):
                    raise AccessDenied("ITAD", resp.status)
                else:
                    raise APIError("ITAD", resp.status)
        except aiohttp.ClientError as e:
            raise NetworkError(f"ITAD connection failed: {e}", e) from e
        except Exception as e:
            logger.error(f"Error looking up ITAD game for {shop}/{game_id}: {e}")
            raise APIError("ITAD", message=str(e)) from e

    async def get_game_overview(self, game_ids: list[str], country: str = "US") -> dict | None:
        """
        Get price overview for a list of game IDs.
        """
        if not self.api_key:
            return None

        url = f"{self.BASE_URL}/games/overview/v2"
        params = {"key": self.api_key, "country": country}
        try:
            async with self.session.post(url, params=params, json=game_ids, headers=HEADERS) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    raise RateLimitExceeded("ITAD")
                elif resp.status in (401, 403):
                    raise AccessDenied("ITAD", resp.status)
                else:
                    raise APIError("ITAD", resp.status, await resp.text())
        except aiohttp.ClientError as e:
            raise NetworkError(f"ITAD connection failed: {e}", e) from e
        except Exception as e:
            logger.error(f"Error getting ITAD overview: {e}")
            raise APIError("ITAD", message=str(e)) from e

    async def get_best_price(self, title: str, country: str = "US") -> dict | None:
        """
        Convenience method to search for a game and get its best price details.
        Returns a dict containing 'game_info' and 'price_info' if found.
        """
        games = await self.search_game(title, limit=1)
        if not games:
            return None

        game = games[0]
        game_id = game["id"]

        overview = await self.get_game_overview([game_id], country=country)
        if not overview or "prices" not in overview or not overview["prices"]:
            return None

        # Match the price info with the game ID (though we only sent one)
        price_info = next((p for p in overview["prices"] if p["id"] == game_id), None)

        if not price_info:
            return None

        return {"game_info": game, "price_info": price_info}

    async def find_game(
        self,
        steam_ids: list[str] | None = None,
        epic_slugs: list[str] | None = None,
        title: str | None = None,
    ) -> dict | None:
        """
        Attempts to find a game using available IDs or title, returning a standardized details dict.
        """
        game = None

        # 1. Try Steam ID
        if steam_ids:
            game = await self.lookup_game("steam", steam_ids[0])

        # 2. Try Epic Slug (via search)
        if not game and epic_slugs:
            search_term = epic_slugs[0].replace("-", " ")
            results = await self.search_game(search_term, limit=1)
            if results:
                game = results[0]

        # 3. Try Title
        if not game and title:
            results = await self.search_game(title, limit=1)
            if results:
                game = results[0]

        if game:
            assets = game.get("assets", {})
            image = (
                assets.get("banner600") or assets.get("banner400") or assets.get("banner300") or assets.get("boxart")
            )
            return {
                "name": game["title"],
                "is_free": True,
                "developers": [],
                "publishers": [],
                "release_date": None,
                "image": image,
                "price_info": "Free to Play",
            }
        return None
