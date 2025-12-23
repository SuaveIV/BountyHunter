from .steam_api_manager import SteamAPIManager
from .store import Store


async def get_game_details(appid: str, manager: SteamAPIManager, store: Store) -> dict | None:
    """
    Retrieves game details, checking the SQLite cache first, then the API.
    """
    # 1. Check Cache
    cached = await store.get_cached_game_details(appid)
    if cached:
        return cached

    # 2. Fetch from API
    details = await manager.fetch_app_details(appid)

    # 3. Store if valid
    if details:
        await store.cache_game_details(appid, details, permanent=True)

    return details
