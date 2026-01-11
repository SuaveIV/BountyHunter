import logging

from .exceptions import (
    AccessDenied,
    APIError,
    GameNotFound,
    NetworkError,
    RateLimitExceeded,
)
from .steam_api_manager import SteamAPIManager
from .store import Store

logger = logging.getLogger(__name__)


async def get_game_details(appid: str, manager: SteamAPIManager, store: Store) -> dict | None:
    """
    Retrieves game details, checking the SQLite cache first, then the API.
    Handles specific exceptions by logging and returning None.
    """
    # 1. Check Cache
    cached = await store.get_cached_game_details(appid)
    if cached:
        return cached

    # 2. Fetch from API
    try:
        details = await manager.fetch_app_details(appid)
    except GameNotFound:
        # Expected for invalid IDs
        logger.debug(f"Steam App {appid} not found.")
        return None
    except RateLimitExceeded as e:
        logger.warning(f"Steam Rate Limit: {e}. Skipping {appid}.")
        return None
    except AccessDenied as e:
        logger.error(f"Steam Access Denied (403): {e}. Check IP reputation/WAF.")
        return None
    except (APIError, NetworkError) as e:
        logger.warning(f"Steam API/Network Error for {appid}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error in Steam get_game_details for {appid}: {e}")
        return None

    # 3. Store if valid
    if details:
        await store.cache_game_details(appid, details, permanent=True)

    return details
