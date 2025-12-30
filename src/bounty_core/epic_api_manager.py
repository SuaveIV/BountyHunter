import logging
import time
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from bounty_core.network import HEADERS

logger = logging.getLogger(__name__)


class EpicAPIManager:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.free_games_cache: list[dict[str, Any]] = []
        self.last_free_games_fetch = 0
        self.cache_duration = 300  # 5 minutes

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

    async def fetch_product_details(self, slug: str) -> dict | None:
        """
        Fetches product details. Tries the CMS API first, then falls back to HTML scraping.
        """
        # 1. Try CMS API
        cms_url = f"https://store-content.ak.epicgames.com/api/en-US/content/products/{slug}"
        try:
            async with self.session.get(cms_url, headers=HEADERS) as resp:
                if resp.status == 200:
                    cms_data = await resp.json()
                    await self._ensure_free_games_cache()
                    is_free = self._check_is_free(slug)
                    return self._parse_api_data(cms_data, is_free)
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
        url = f"https://store.epicgames.com/en-US/p/{slug}"
        try:
            async with self.session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.warning(f"Epic Store page returned {resp.status} for {slug}")
                    return None
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            # Name
            name = "Unknown Epic Game"
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                content = og_title["content"]
                if isinstance(content, str):
                    name = content.replace(" | Download and Buy Today - Epic Games Store", "").strip()
                elif isinstance(content, list) and content and isinstance(content[0], str):
                    name = content[0].replace(" | Download and Buy Today - Epic Games Store", "").strip()

            # Image
            image = None
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                image = og_image["content"]

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

        except Exception as e:
            logger.error(f"Error scraping Epic Store page for {slug}: {e}")
            return None

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
