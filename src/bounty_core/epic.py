from .epic_api_manager import EpicAPIManager
from .store import Store


async def get_game_details(slug: str, manager: EpicAPIManager, store: Store) -> dict | None:
    """
    Retrieves game details, checking the SQLite cache first, then the API.
    """
    return await store.get_cached_or_fetch("epic", slug, lambda: manager.fetch_product_details(slug), permanent=True)
