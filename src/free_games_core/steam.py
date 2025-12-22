import asyncio
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

async def fetch_game_details(steam_app_id: str) -> Optional[Dict]:
    """
    Basic Steam details fetcher stub. Replace with full Steam API/HTML scraping as needed.
    Returns dict with keys: 'name', 'store_url', 'image', 'price', 'is_free'
    """
    await asyncio.sleep(0.01)  # placeholder for network call
    # Minimal stubbed response
    return {
        "name": f"Steam Game {steam_app_id}",
        "store_url": f"https://store.steampowered.com/app/{steam_app_id}",
        "image": None,
        "price": "Free",
        "is_free": True,
    }