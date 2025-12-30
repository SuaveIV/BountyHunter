import logging
from typing import Any

import aiohttp

from bounty_core.network import HEADERS

logger = logging.getLogger(__name__)


class ItadAPIManager:
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
                else:
                    logger.warning(f"ITAD Search failed: {resp.status} - {await resp.text()}")
                    return []
        except Exception as e:
            logger.error(f"Error searching ITAD for {title}: {e}")
            return []

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
                else:
                    logger.warning(f"ITAD Overview failed: {resp.status} - {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"Error getting ITAD overview: {e}")
            return None

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
