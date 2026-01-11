import logging

import aiohttp

from bounty_core.exceptions import (
    AccessDenied,
    APIError,
    GameNotFound,
    NetworkError,
    RateLimitExceeded,
)
from bounty_core.network import HEADERS
from bounty_core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class SteamAPIManager:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        # Steam allows ~200 requests per 5 minutes -> ~0.66 req/s.
        # We'll be conservative with 0.5 req/s (1 request every 2 seconds)
        self.rate_limiter = RateLimiter(calls_per_second=0.5)

    async def fetch_app_details(self, appid: str) -> dict | None:
        url = "https://store.steampowered.com/api/appdetails"
        params = {"appids": appid, "cc": "us", "l": "en"}

        await self.rate_limiter.acquire()

        try:
            async with self.session.get(url, params=params, headers=HEADERS) as resp:
                if resp.status == 429:
                    logger.warning(f"Steam API Rate Limit hit for {appid}.")
                    # Steam doesn't always send Retry-After, assume 60s if hitting 429
                    retry_after = 60.0
                    if "Retry-After" in resp.headers:
                        try:
                            retry_after = float(resp.headers["Retry-After"])
                        except ValueError:
                            pass
                    raise RateLimitExceeded("Steam", retry_after=retry_after)

                if resp.status == 403 or resp.status == 401:
                    raise AccessDenied("Steam", resp.status)

                if resp.status != 200:
                    raise APIError("Steam", resp.status, await resp.text())

                data = await resp.json()

                # Steam API returns 200 even if app doesn't exist, checking "success" flag
                if not data or str(appid) not in data:
                    raise APIError("Steam", 200, "Invalid JSON structure")

                app_data = data[str(appid)]
                if not app_data.get("success"):
                    # This is effectively a 404
                    raise GameNotFound(appid, "Steam")

                result = self._parse_store_data(app_data["data"])
                result["store_url"] = f"https://store.steampowered.com/app/{appid}/"
                return result

        except aiohttp.ClientError as e:
            raise NetworkError(f"Steam connection failed: {e}", e) from e
        except (RateLimitExceeded, AccessDenied, GameNotFound, APIError):
            raise
        except Exception as e:
            logger.error(f"Unexpected exception fetching steam details for {appid}: {e}")
            raise APIError("Steam", message=str(e)) from e

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
