import logging
import time
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from bounty_core.exceptions import (
    AccessDenied,
    APIError,
    BountyException,
    GameNotFound,
    NetworkError,
    RateLimitExceeded,
    ScrapingError,
)
from bounty_core.network import HEADERS
from bounty_core.parser import extract_og_data
from bounty_core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

#: Placeholder used when the store page loads but exposes no metadata.
UNKNOWN_EPIC_NAME = "Unknown Epic Game"


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

        store_url = f"https://store.epicgames.com/en-US/p/{slug}"

        # 1. Try CMS API
        cms_url = f"https://store-content.ak.epicgames.com/api/en-US/content/products/{slug}"
        try:
            async with self.session.get(cms_url, headers=HEADERS) as resp:
                if resp.status == 200:
                    cms_data = await resp.json()
                    await self._ensure_free_games_cache()
                    is_free = self._check_is_free(slug)
                    result = self._parse_api_data(cms_data, is_free)
                    # BUG FIX: store_url was never set, causing the embed store-detection
                    # to fall through to the generic branch regardless of the game's platform.
                    result["store_url"] = store_url
                    return result
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
        scraped = None
        try:
            scraped = await self._scrape_store_page(slug)
        except BountyException as e:
            # The store page sits behind a WAF for a lot of products: a 403, or a 200 that
            # renders client side and carries no og:title.
            logger.warning(f"Epic store page unusable for {slug} ({type(e).__name__}: {e})")

        if self._has_name(scraped):
            return scraped

        # 3. Fallback: the promotions feed. It is the one Epic endpoint that answers
        # consistently, and it carries the title, description and key art for free titles.
        promoted = await self._promotion_details(slug)
        if promoted:
            return promoted

        # A details dict with no usable name would block the ITAD and generic fallbacks
        # upstream, which is how these listings ended up as bare text messages.
        return None

    @staticmethod
    def _has_name(details: dict | None) -> bool:
        name = str((details or {}).get("name") or "").strip()
        return bool(name) and name != UNKNOWN_EPIC_NAME

    @staticmethod
    def _promotion_slugs(element: dict) -> set[str]:
        """Every slug an Epic catalog element answers to."""
        slugs = set()

        for mapping in element.get("offerMappings") or []:
            page = (mapping or {}).get("page") or {}
            page_slug = page.get("slug")
            if page_slug:
                slugs.add(str(page_slug).strip("/").lower())

        for key in ("productSlug", "urlSlug"):
            value = element.get(key)
            if value:
                slugs.add(str(value).removesuffix("/home").strip("/").lower())

        return slugs

    def _find_promotion(self, slug: str) -> dict | None:
        """Find the cached promotions entry for a slug."""
        wanted = slug.strip().strip("/").lower()
        if not wanted:
            return None

        for element in self.free_games_cache:
            if wanted in self._promotion_slugs(element):
                return element

        return None

    @staticmethod
    def _promotion_image(element: dict) -> str | None:
        for wanted in ("OfferImageWide", "DieselStoreFrontWide", "Thumbnail"):
            for image in element.get("keyImages") or []:
                if (image or {}).get("type") == wanted and image.get("url"):
                    return str(image["url"])
        return None

    async def _promotion_details(self, slug: str) -> dict | None:
        """
        Build details from the promotions feed.

        Epic 404s its content API for newer products and WAFs or client-renders the store
        page, so for a giveaway this feed is the reliable source of name, description and art.
        """
        await self._ensure_free_games_cache()

        element = self._find_promotion(slug)
        name = str((element or {}).get("title") or "").strip()
        if not element or not name:
            return None

        is_free = self._check_is_free(slug)
        return {
            "name": name,
            "is_free": is_free,
            "developers": [],
            "publishers": [],
            "release_date": None,
            "image": self._promotion_image(element),
            "description": element.get("description"),
            "price_info": "Free to Play" if is_free else "Check Store",
            "store_url": f"https://store.epicgames.com/en-US/p/{slug}",
        }

    def _check_is_free(self, slug: str) -> bool:
        element = self._find_promotion(slug)
        if not element:
            return False

        promotions = element.get("promotions") or {}
        return bool(promotions.get("promotionalOffers"))

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

            name = UNKNOWN_EPIC_NAME
            if og_data["title"]:
                name = og_data["title"].replace(" | Download and Buy Today - Epic Games Store", "").strip()

            image = og_data["image"]

            # Price / Free status
            is_free = False
            price_str = "Check Store"

            # Heuristic: Check if we can find "Free" in price areas
            if soup.find(string="Free") or soup.find(string="Get"):
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
                # BUG FIX: store_url was missing from this path too
                "store_url": url,
            }

        except aiohttp.ClientError as e:
            raise NetworkError(f"Epic Store connection failed: {e}", e) from e
        except (GameNotFound, RateLimitExceeded, AccessDenied, APIError):
            raise
        except Exception as e:
            logger.error(f"Error scraping Epic Store page for {slug}: {e}")
            raise ScrapingError("Epic Store", slug, str(e)) from e

    def _parse_api_data(self, data: dict, is_free: bool) -> dict:
        # Note: store_url is intentionally NOT set here; it is set by the caller
        # (fetch_product_details) which has access to the slug.
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
