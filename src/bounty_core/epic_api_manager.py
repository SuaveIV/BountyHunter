import logging
import time
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from bounty_core.exceptions import (
    AccessDenied,
    APIError,
    GameNotFound,
    NetworkError,
    RateLimitExceeded,
    ScrapingError,
)
from bounty_core.network import HEADERS
from bounty_core.parser import extract_og_data
from bounty_core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class EpicAPIManager:
    """
    Manages interactions with the Epic Games Store.
    Combines CMS API calls with HTML scraping as a fallback.
    Tracks currently free games via the Promotions API.
    """

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.free_games_cache: list[dict[str, Any]] = []
        self.last_free_games_fetch = 0
        self.cache_duration = 300  # 5 minutes
        # Epic is generally robust, but scraping too fast can trigger WAF.
        # 1 request per second is safe.
        self.rate_limiter = RateLimiter(calls_per_second=1.0)

    async def _ensure_free_games_cache(self):
        """
        Updates the local cache of currently free games from the Epic Promotions API.
        """
        now = time.time()
        if now - self.last_free_games_fetch < self.cache_duration and self.free_games_cache:
            return

        url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
        try:
            async with self.session.get(url, headers=HEADERS) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # The structure is deeply nested
                    self.free_games_cache = (
                        data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
                    )
                    self.last_free_games_fetch = now
        except Exception as e:
            logger.error(f"Failed to update Epic free games cache: {e}")
            # We don't raise here to avoid blocking product details fetch if just this fails

    async def fetch_product_details(self, slug: str) -> dict | None:
        """
        Fetches product details. Tries the CMS API first, then falls back to HTML scraping.
        Raises BountyException subclasses on failure.
        """
        await self.rate_limiter.acquire()

        # 1. Try CMS API
        cms_url = f"https://store-content.ak.epicgames.com/api/en-US/content/products/{slug}"
        try:
            async with self.session.get(cms_url, headers=HEADERS) as resp:
                if resp.status == 200:
                    cms_data = await resp.json()
                    await self._ensure_free_games_cache()
                    is_free = self._check_is_free(slug)
                    return self._parse_api_data(cms_data, is_free)
                elif resp.status == 404:
                    # Not found in CMS, might still exist as a page to scrape
                    pass
                elif resp.status == 429:
                    raise RateLimitExceeded("Epic API")
        except aiohttp.ClientError as e:
            logger.warning(f"Epic CMS API connection error for {slug}: {e}")
        except Exception as e:
            logger.warning(f"Epic CMS API failed for {slug}: {e}")

        # 2. Fallback: Scrape HTML
        return await self._scrape_store_page(slug)

    def _check_is_free(self, slug: str) -> bool:
        for game in self.free_games_cache:
            game_slug = game.get("productSlug") or game.get("urlSlug")
            if game_slug == slug:
                promotions = game.get("promotions") or {}
                if promotions.get("promotionalOffers"):
                    return True
        return False

    async def _scrape_store_page(self, slug: str) -> dict | None:
        await self.rate_limiter.acquire()

        url = f"https://store.epicgames.com/en-US/p/{slug}"
        try:
            async with self.session.get(url, headers=HEADERS) as resp:
                if resp.status == 404:
                    raise GameNotFound(slug, "Epic Store")
                if resp.status == 429:
                    raise RateLimitExceeded("Epic Store")
                if resp.status == 403:
                    raise AccessDenied("Epic Store", resp.status)
                if resp.status != 200:
                    raise APIError("Epic Store", resp.status)

                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            # Extract Name and Image via shared helper
            og_data = extract_og_data(soup)

            name = "Unknown Epic Game"
            if og_data["title"]:
                name = og_data["title"].replace(" | Download and Buy Today - Epic Games Store", "").strip()

            image = og_data["image"]

            # Price / Free status
            # Check for "Free" text or "Download" button
            is_free = False
            price_str = "Check Store"

            # Heuristic: Check if we can find "Free" in price areas
            # This is hard to pinpoint without exact classes which change
            # But usually "Free" is visible text.
            if soup.find(string="Free") or soup.find(string="Get"):
                # "Get" button usually implies free or owned
                # We can cross-reference with our free_games_cache
                await self._ensure_free_games_cache()
                if self._check_is_free(slug):
                    is_free = True
                    price_str = "Free to Play"

            return {
                "name": name,
                "is_free": is_free,
                "developers": [],
                "publishers": [],
                "release_date": None,
                "image": image,
                "price_info": price_str,
            }

        except aiohttp.ClientError as e:
            raise NetworkError(f"Epic Store connection failed: {e}", e) from e
        except (GameNotFound, RateLimitExceeded, AccessDenied, APIError):
            raise
        except Exception as e:
            logger.error(f"Error scraping Epic Store page for {slug}: {e}")
            raise ScrapingError("Epic Store", slug, str(e)) from e

    def _parse_api_data(self, data: dict, is_free: bool) -> dict:
        parsed = {
            "name": data.get("productName") or data.get("_title"),
            "is_free": is_free,
            "developers": [],
            "publishers": [],
            "release_date": None,
            "image": None,
            "price_info": "Free to Play" if is_free else "Check Store",
        }

        # Extract Dev/Pub from customAttributes
        for attr in data.get("customAttributes", []):
            key = attr.get("key")
            val = attr.get("value")
            if key == "developerName":
                parsed["developers"].append(val)
            elif key == "publisherName":
                parsed["publishers"].append(val)

        # Extract Image
        for img in data.get("keyImages", []):
            if img.get("type") in ("OfferImageWide", "DieselStoreFrontWide", "Thumbnail"):
                parsed["image"] = img.get("url")
                if img.get("type") in ("OfferImageWide", "DieselStoreFrontWide"):
                    break

        return parsed
