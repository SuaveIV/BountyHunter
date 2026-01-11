import logging

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


class GogAPIManager:
    """
    Manages fetching and parsing game details from GOG.com.
    Uses HTML scraping via BeautifulSoup.
    """

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        # GOG is protected by Cloudflare. Conservative rate limit.
        self.rate_limiter = RateLimiter(calls_per_second=0.2)  # 1 request every 5 seconds

    async def fetch_game_details(self, url: str) -> dict | None:
        """
        Fetches the GOG store page and extracts details.

        Args:
            url: The full URL to the GOG game page.

        Returns:
            A dictionary containing game details, or None.
        """
        await self.rate_limiter.acquire()

        try:
            # Add Cookie header if needed, but for now stick to standard HEADERS
            async with self.session.get(url, headers=HEADERS) as resp:
                if resp.status == 404:
                    raise GameNotFound(url, "GOG")
                if resp.status == 429:
                    raise RateLimitExceeded("GOG")
                if resp.status == 403:
                    raise AccessDenied("GOG", resp.status)
                if resp.status != 200:
                    raise APIError("GOG", resp.status)

                text = await resp.text()
                return self._parse_html(text, url)

        except aiohttp.ClientError as e:
            raise NetworkError(f"GOG connection failed: {e}", e) from e
        except (GameNotFound, RateLimitExceeded, AccessDenied, APIError):
            raise
        except Exception as e:
            logger.error(f"Error fetching GOG details for {url}: {e}")
            raise ScrapingError("GOG", url, str(e)) from e

    def _parse_html(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        og_data = extract_og_data(soup)

        name = og_data["title"] or "Unknown GOG Game"
        image = og_data["image"]

        # GOG specific cleanup
        if name and " on GOG.com" in name:
            name = name.replace(" on GOG.com", "")

        is_free = False
        price_str = "Check Store"

        # Try to find price
        # GOG HTML structure is complex and changes.
        # Look for "free" in product actions or price labels.
        # This is a heuristic.

        # Look for JSON-LD which GOG sometimes provides
        # ... (Similar to PS/Itch if available, but GOG uses microdata mostly)

        # Simple text search for now
        body_text = soup.get_text().lower()
        if "free" in body_text and "add to cart" in body_text:
            # Very weak heuristic, but better than nothing.
            # Ideally we check specific classes like `.product-actions-price__final-amount`
            pass

        # Check for specific price element (subject to change)
        price_el = soup.find(class_="product-actions-price__final-amount")
        if price_el:
            price_text = price_el.get_text().strip()
            if price_text == "0.00" or "free" in price_text.lower():
                is_free = True
                price_str = "Free"
            else:
                price_str = price_text

        return {
            "name": name,
            "is_free": is_free,
            "developers": [],
            "publishers": ["GOG"],
            "release_date": None,
            "image": image,
            "price_info": price_str,
            "store_url": url,
        }
