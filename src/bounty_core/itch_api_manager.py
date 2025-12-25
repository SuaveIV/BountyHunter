import json
import logging
import re

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class ItchAPIManager:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_game_details(self, url: str) -> dict | None:
        try:
            async with self.session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    logger.warning(f"Itch.io returned {resp.status} for {url}")
                    return None
                text = await resp.text()
                return self._parse_html(text, url)
        except Exception as e:
            logger.error(f"Error fetching itch.io details for {url}: {e}")
            return None

    def _parse_html(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Try to parse JSON-LD (Structured Data)
        script_tag = soup.find("script", type="application/ld+json")
        if script_tag and script_tag.string:
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
        name = "Unknown Itch Game"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            name = og_title["content"]

        image = None
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image = og_image["content"]

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
