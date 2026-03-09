from .ps_api_manager import PSAPIManager
from .store import Store


async def get_game_details(url: str, manager: PSAPIManager, store: Store) -> dict | None:
    """
    Retrieves game details, checking the SQLite cache first, then the API.
    """
    return await store.get_cached_or_fetch("ps", url, lambda: manager.fetch_game_details(url), permanent=True)
