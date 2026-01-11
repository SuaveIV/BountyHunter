import logging
from typing import Any

from .itad_api_manager import ItadAPIManager
from .parser import extract_game_title

logger = logging.getLogger(__name__)


async def enhance_details_with_itad(details: dict[str, Any], itad_manager: ItadAPIManager | None) -> None:
    """
    Attempts to fetch missing metadata (currently just image) from ITAD
    for any given details dictionary. Modifies details in-place.
    """
    if not itad_manager or not itad_manager.api_key:
        return

    title = details.get("name")
    if not title or title == "Free Game":
        return

    # If image is missing, try to find it
    if not details.get("image"):
        try:
            results = await itad_manager.search_game(title, limit=1)
            if results:
                game_info = results[0]
                assets = game_info.get("assets", {})
                banner = assets.get("banner400") or assets.get("banner300") or assets.get("boxArt")
                if banner:
                    details["image"] = banner
                    logger.info(f"Fetched image for '{title}' from ITAD")
        except Exception as e:
            logger.warning(f"Failed to fetch ITAD image for '{title}': {e}")


async def get_fallback_details(
    links: list[str], text: str, itad_manager: ItadAPIManager | None, image: str | None = None
) -> dict[str, Any]:
    """
    Generate basic details from links/text when no specific API manager is available.
    Optionally attempts to fetch missing image from ITAD.
    """
    fallback_url = None
    for link in links:
        if any(d in link for d in ["gog.com", "amazon.com", "onstove.com", "stove.com"]):
            fallback_url = link
            break
    if not fallback_url and links:
        fallback_url = links[0]

    if not fallback_url:
        return {}

    title = extract_game_title(text) or "Free Game"

    # Heuristic: if title wasn't extracted and text is short, assume text is the title
    if title == "Free Game" and text and len(text) < 50 and "http" not in text:
        title = text

    details = {
        "name": title,
        "store_url": fallback_url,
        "image": image,
    }

    # Use the shared enhancement function to try getting an image if missing
    if not details["image"] and itad_manager:
        await enhance_details_with_itad(details, itad_manager)

    return details
