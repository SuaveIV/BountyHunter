import json
import logging

import aiohttp
from bs4 import BeautifulSoup

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
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"PS Store returned {resp.status} for {url}")
                    return None
                text = await resp.text()
                return self._parse_html(text, url)
        except Exception as e:
            logger.error(f"Error fetching PS Store details for {url}: {e}")
            return None

    def _parse_html(self, html: str, url: str) -> dict:
        """Extracts name, image, and price from the HTML body."""
        soup = BeautifulSoup(html, "html.parser")

        # 1. Name Extraction (Open Graph Title)
        name = "Unknown PS Game"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            content = og_title["content"]
            # Handle both single string and list cases
            title_text = content[0] if isinstance(content, list) else content
            name = title_text.replace(" | PlayStation Store", "").strip()

        # 2. Image Extraction (Open Graph Image)
        image = None
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            content = og_image["content"]
            image = content[0] if isinstance(content, list) else content

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
