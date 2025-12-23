from .epic_api_manager import EpicAPIManager
from .store import Store


async def get_game_details(slug: str, manager: EpicAPIManager, store: Store) -> dict | None:
    """
    Retrieves game details, checking the SQLite cache first, then the API.
    """
    # 1. Check Cache
    cached = await store.get_cached_epic_details(slug)
    if cached:
        return cached

    # 2. Fetch from API
    details = await manager.fetch_product_details(slug)

    # 3. Store if valid
    if details:
        await store.cache_epic_details(slug, details, permanent=True)

    return details
