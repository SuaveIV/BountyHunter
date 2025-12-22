import asyncio
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta

from .steam_api_manager import SteamAPIManager

logger = logging.getLogger(__name__)

# Simple in-memory cache for fetched Steam appdetails.
# Structure: { appid: { "fetched_at": datetime, "data": {...} } }
# This is intentionally simple; for production, persist to DB or use a proper cache.
_CACHE: Dict[str, Dict] = {}
CACHE_TTL = timedelta(hours=24)  # time to keep cache entries


def get_cached_game_details(app_id: str) -> Optional[Dict]:
    entry = _CACHE.get(str(app_id))
    if not entry:
        return None
    if datetime.utcnow() - entry["fetched_at"] > CACHE_TTL:
        # stale
        del _CACHE[str(app_id)]
        return None
    return entry["data"]


def cache_game_details(app_id: str, data: Dict) -> None:
    _CACHE[str(app_id)] = {"fetched_at": datetime.utcnow(), "data": data}


async def fetch_game_details(app_id: str, steam_api_manager: Optional[SteamAPIManager] = None) -> Optional[Dict]:
    """
    Fetch Steam store appdetails for app_id.

    - Uses an in-memory cache to avoid repeated calls.
    - Requires (or will create) a SteamAPIManager to perform rate-limited requests.

    Returns the 'data' object from the store API, or None on failure.
    """
    # 1) Check cache
    cached = get_cached_game_details(app_id)
    if cached:
        return cached

    # 2) Prepare manager
    manager = steam_api_manager or SteamAPIManager()
    try:
        await manager.rate_limit_steam_store_api()
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
        json_resp = await manager.make_request_with_retry(url, timeout=15)
        if not json_resp:
            logger.debug("No JSON received for app %s", app_id)
            return None

        # JSON is shaped as { "<app_id>": { "success": True, "data": {...} }, ... }
        item = json_resp.get(str(app_id))
        if not item:
            logger.debug("No item for app %s in response", app_id)
            return None
        if not item.get("success"):
            logger.debug("Steam reported success=false for app %s", app_id)
            return None
        data = item.get("data")
        if not data:
            logger.debug("No data for app %s", app_id)
            return None

        # Cache and return the data
        cache_game_details(app_id, data)
        return data
    except Exception as e:
        logger.exception("Error fetching game details for %s: %s", app_id, e)
        return None
    finally:
        # If manager created its own session, you can optionally close it here.
        # If you passed the bot's shared session to SteamAPIManager, do not close it here.
        pass