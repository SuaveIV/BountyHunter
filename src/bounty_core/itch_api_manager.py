import json
import logging
import re

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


class ItchAPIManager:
    """
    Manages fetching and parsing game details from itch.io.
    Primarily uses HTML scraping as there is no public store API for this data.
    """

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        # Itch.io is sensitive to scraping. 1 request per 2 seconds is polite.
        self.rate_limiter = RateLimiter(calls_per_second=0.5)

    async def fetch_game_details(self, url: str) -> dict | None:
        """
        Fetches the game page and extracts details via scraping.

        Args:
            url: The full URL to the itch.io game page.

        Returns:
            A dictionary containing game details, or None on failure.

        Raises:
            BountyException subclasses on error (RateLimit, NotFound, etc).
        """
        await self.rate_limiter.acquire()
        try:
            async with self.session.get(url, headers=HEADERS) as resp:
                if resp.status == 404:
                    raise GameNotFound(url, "Itch.io")
                if resp.status == 429:
                    raise RateLimitExceeded("Itch.io")
                if resp.status == 403:
                    raise AccessDenied("Itch.io", resp.status)
                if resp.status != 200:
                    raise APIError("Itch.io", resp.status)

                text = await resp.text()
                return self._parse_html(text, url)
        except aiohttp.ClientError as e:
            raise NetworkError(f"Itch.io connection failed: {e}", e) from e
        except (GameNotFound, RateLimitExceeded, AccessDenied, APIError):
            raise
        except Exception as e:
            logger.error(f"Error fetching itch.io details for {url}: {e}")
            raise ScrapingError("Itch.io", url, str(e)) from e

    def _parse_html(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Try to parse JSON-LD (Structured Data)
        script_tags = soup.find_all("script", type="application/ld+json")
        for script_tag in script_tags:
            if script_tag.string:
                try:
                    data = json.loads(script_tag.string)
                    # Ensure it's the game object
                    if data.get("@type") in ("SoftwareApplication", "VideoGame", "Product"):
                        offers = data.get("offers", {})
                        price = offers.get("price", "0.00")
                        currency = offers.get("priceCurrency", "USD")

                        # Itch uses "0.00" for free games
                        is_free = False
                        try:
                            is_free = float(price) == 0.0
                        except ValueError:
                            pass

                        author = data.get("author", {})
                        if isinstance(author, dict):
                            developer = author.get("name", "Unknown")
                        else:
                            developer = "Unknown"

                        return {
                            "name": data.get("name", "Unknown Itch Game"),
                            "is_free": is_free,
                            "developers": [developer],
                            "publishers": ["itch.io"],
                            "release_date": data.get("datePublished"),
                            "image": data.get("image"),
                            "price_info": "Free to Play" if is_free else f"{price} {currency}",
                        }
                except Exception as e:
                    logger.warning(f"Failed to parse JSON-LD for {url}: {e}")

        # 2. Fallback: BS4 Scraping
        og_data = extract_og_data(soup)
        name = og_data["title"] or "Unknown Itch Game"
        image = og_data["image"]

        # Developer from URL (subdomain)
        dev_match = re.search(r"https?://([^\.]+)\.itch\.io", url)
        developer = dev_match.group(1) if dev_match else "Unknown"

        # Check for "Download" button vs "Buy" button
        is_free = False
        price_str = "Check Store"

        buy_btn = soup.find(class_=re.compile("buy_btn"))
        if buy_btn:
            btn_text = buy_btn.get_text().strip().lower()
            if "download" in btn_text or "name your own price" in btn_text:
                is_free = True
                price_str = "Free to Play"

        return {
            "name": name,
            "is_free": is_free,
            "developers": [developer],
            "publishers": ["itch.io"],
            "release_date": None,
            "image": image,
            "price_info": price_str,
        }
