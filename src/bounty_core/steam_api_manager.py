import asyncio
import logging
import time

import aiohttp

from bounty_core.network import HEADERS

logger = logging.getLogger(__name__)


class SteamAPIManager:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.last_call = 0
        self.rate_limit_delay = 1.5  # Conservative delay to avoid 429s

    async def fetch_app_details(self, appid: str) -> dict | None:
        url = "https://store.steampowered.com/api/appdetails"
        params = {"appids": appid, "cc": "us", "l": "en"}

        # Simple leaky bucket
        now = time.time()
        if now - self.last_call < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - (now - self.last_call))

        self.last_call = time.time()

        try:
            async with self.session.get(url, params=params, headers=HEADERS) as resp:
                if resp.status == 429:
                    logger.warning(f"Steam API Rate Limit hit for {appid}. Backing off.")
                    await asyncio.sleep(10)
                    return None

                data = await resp.json()
                if data and str(appid) in data and data[str(appid)]["success"]:
                    result = self._parse_store_data(data[str(appid)]["data"])
                    result["store_url"] = f"https://store.steampowered.com/app/{appid}/"
                    return result
        except Exception as e:
            logger.error(f"Exception fetching steam details for {appid}: {e}")
        return None

    def _parse_store_data(self, game_info: dict) -> dict:
        parsed_info = {
            "name": game_info.get("name"),
            "is_free": game_info.get("is_free"),
            "developers": game_info.get("developers", []),
            "publishers": game_info.get("publishers", []),
            "release_date": game_info.get("release_date", {}).get("date"),
            "image": game_info.get("header_image"),
            "price_info": None,
        }

        if parsed_info["is_free"]:
            parsed_info["price_info"] = "Free to Play"
        elif "price_overview" in game_info:
            price_data = game_info["price_overview"]
            parsed_info["price_info"] = {
                "current_price": price_data.get("final_formatted"),
                "original_price": price_data.get("initial_formatted"),
                "discount_percent": price_data.get("discount_percent"),
                "currency": price_data.get("currency"),
            }
        else:
            parsed_info["price_info"] = "Not Priced / Unreleased"

        return parsed_info
