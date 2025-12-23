import json
import logging
import re

import aiohttp

logger = logging.getLogger(__name__)


class ItchAPIManager:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_game_details(self, url: str) -> dict | None:
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
                return self._parse_html(text, url)
        except Exception as e:
            logger.error(f"Error fetching itch.io details for {url}: {e}")
            return None

    def _parse_html(self, html: str, url: str) -> dict:
        # 1. Try to parse JSON-LD (Structured Data)
        # This is the most reliable way to get price and author info
        ld_json_match = re.search(r'<script type="application/ld\+json">\s*({.*?})\s*</script>', html, re.DOTALL)
        if ld_json_match:
            try:
                data = json.loads(ld_json_match.group(1))
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

                    return {
                        "name": data.get("name", "Unknown Itch Game"),
                        "is_free": is_free,
                        "developers": [data.get("author", {}).get("name", "Unknown")],
                        "publishers": ["itch.io"],
                        "release_date": data.get("datePublished"),
                        "image": data.get("image"),
                        "price_info": "Free to Play" if is_free else f"{price} {currency}",
                    }
            except Exception as e:
                logger.warning(f"Failed to parse JSON-LD for {url}: {e}")

        # 2. Fallback: Regex Scraping
        og_title = re.search(r'<meta property="og:title" content="(.*?)">', html)
        name = og_title.group(1) if og_title else "Unknown Itch Game"

        og_image = re.search(r'<meta property="og:image" content="(.*?)">', html)
        image = og_image.group(1) if og_image else None

        # Developer from URL (subdomain)
        dev_match = re.search(r"https?://([^\.]+)\.itch\.io", url)
        developer = dev_match.group(1) if dev_match else "Unknown"

        # Check for "Download" button vs "Buy" button
        is_free = False
        price_str = "Check Store"

        # Look for the buy button text
        buy_btn_match = re.search(r'class=["\'].*?buy_btn.*?["\'][^>]*>(.*?)<', html, re.IGNORECASE | re.DOTALL)
        if buy_btn_match:
            btn_text = buy_btn_match.group(1).strip().lower()
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
