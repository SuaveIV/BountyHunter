from .itch_api_manager import ItchAPIManager
from .store import Store


async def get_game_details(url: str, manager: ItchAPIManager, store: Store) -> dict | None:
    """
    Retrieves game details, checking the SQLite cache first, then the API.
    """
    # 1. Check Cache
    cached = await store.get_cached_itch_details(url)
    if cached:
        return cached

    # 2. Fetch from API
    details = await manager.fetch_game_details(url)

    # 3. Store if valid
    if details:
        await store.cache_itch_details(url, details, permanent=True)

    return details
