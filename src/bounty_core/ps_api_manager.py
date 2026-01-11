import json
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

logger = logging.getLogger(__name__)


class PSAPIManager:
    """
    Manages fetching and parsing game details from the PlayStation Store.
    """

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_game_details(self, url: str) -> dict | None:
        """Fetches the page content and returns parsed game data."""
        try:
            async with self.session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 404:
                    raise GameNotFound(url, "PS Store")
                if resp.status == 429:
                    raise RateLimitExceeded("PS Store")
                if resp.status == 403:
                    raise AccessDenied("PS Store", resp.status)
                if resp.status != 200:
                    raise APIError("PS Store", resp.status)

                text = await resp.text()
                return self._parse_html(text, url)
        except aiohttp.ClientError as e:
            raise NetworkError(f"PS Store connection failed: {e}", e) from e
        except (GameNotFound, RateLimitExceeded, AccessDenied, APIError):
            raise
        except Exception as e:
            logger.error(f"Error fetching PS Store details for {url}: {e}")
            raise ScrapingError("PS Store", url, str(e)) from e

    def _parse_html(self, html: str, url: str) -> dict:
        """Extracts name, image, and price from the HTML body."""
        soup = BeautifulSoup(html, "html.parser")

        # 1. Open Graph Extraction
        og_data = extract_og_data(soup)

        name = "Unknown PS Game"
        if og_data["title"]:
            name = og_data["title"].replace(" | PlayStation Store", "").strip()

        image = og_data["image"]

        # 3. Price & Is Free (JSON-LD Parsing)
        is_free = False
        price_str = "Check Store"

        # Search for structured data scripts
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                # Check if this specific script describes the product
                if data.get("@type") in ["Product", "VideoGame"]:
                    # Fallback for Name and Image from JSON-LD
                    if name == "Unknown PS Game":
                        name = data.get("name", name)

                    if not image:
                        img_data = data.get("image")
                        if isinstance(img_data, list):
                            image = img_data[0]
                        elif isinstance(img_data, str):
                            image = img_data

                    offers = data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}

                    price = offers.get("price")
                    currency = offers.get("priceCurrency", "")

                    if price is not None:
                        try:
                            if float(price) == 0:
                                is_free = True
                                price_str = "Free"
                            else:
                                price_str = f"{price} {currency}".strip()
                        except ValueError:
                            pass
                    break  # Exit loop once we find the price
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback for "Free" status if JSON-LD fails
        if not is_free and price_str == "Check Store":
            # Search text for 'Free' strings
            if soup.find(string=["Free", "Free to Play"]):
                is_free = True
                price_str = "Free"

        return {
            "name": name,
            "is_free": is_free,
            "developers": [],
            "publishers": ["Sony Interactive Entertainment"],
            "release_date": None,
            "image": image,
            "price_info": price_str,
            "store_url": url,
        }
