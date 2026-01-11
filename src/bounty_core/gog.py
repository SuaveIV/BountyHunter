import logging

from .exceptions import (
    AccessDenied,
    APIError,
    GameNotFound,
    NetworkError,
    RateLimitExceeded,
)
from .gog_api_manager import GogAPIManager
from .store import Store

logger = logging.getLogger(__name__)


async def get_game_details(url: str, manager: GogAPIManager, store: Store) -> dict | None:
    """
    Retrieves game details from GOG, checking cache first.
    """
    # 1. Check Cache
    cached = await store.get_cached_gog_details(url)
    if cached:
        return cached

    # 2. Fetch from API
    try:
        details = await manager.fetch_game_details(url)
    except GameNotFound:
        logger.debug(f"GOG Game {url} not found.")
        return None
    except RateLimitExceeded as e:
        logger.warning(f"GOG Rate Limit: {e}.")
        return None
    except AccessDenied as e:
        logger.error(f"GOG Access Denied (403): {e}.")
        return None
    except (APIError, NetworkError) as e:
        logger.warning(f"GOG API/Network Error for {url}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error in GOG get_game_details: {e}")
        return None

    # 3. Store if valid
    if details:
        await store.cache_gog_details(url, details, permanent=True)

    return details
