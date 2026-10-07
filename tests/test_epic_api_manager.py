from unittest.mock import AsyncMock, MagicMock

import pytest

from bounty_core.epic_api_manager import UNKNOWN_EPIC_NAME, EpicAPIManager

SLUG = "buried-stars"

PROMOTIONS_PAYLOAD = {
    "data": {
        "Catalog": {
            "searchStore": {
                "elements": [
                    {
                        "id": "af4c34934afe4db0870b8a1d82dceb94",
                        "title": "BURIED STARS",
                        "description": "A mystery adventure set at the collapse site of a live show.",
                        "urlSlug": SLUG,
                        "productSlug": None,
                        "offerMappings": [None],
                        "keyImages": [
                            {"type": "OfferImageTall", "url": "https://cdn.example/tall.jpg"},
                            {"type": "OfferImageWide", "url": "https://cdn.example/wide.jpg"},
                        ],
                        "promotions": {
                            "promotionalOffers": [
                                {"promotionalOffers": [{"discountSetting": {"discountPercentage": 0}}]}
                            ]
                        },
                    }
                ]
            }
        }
    }
}

# A store page that renders client side: 200, no og:title.
JS_SHELL_HTML = "<html><head><title></title></head><body><div id='root'></div></body></html>"

RENDERED_HTML = (
    "<html><head>"
    "<meta property='og:title' content='BURIED STARS | Download and Buy Today - Epic Games Store'>"
    "</head><body>BURIED STARS</body></html>"
)


class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = ""):
        self.status = status
        self.payload = payload
        self._text = text
        self.headers: dict[str, str] = {}

    async def json(self, content_type=None):
        return self.payload

    async def text(self):
        return self._text


class FakeGet:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


class RoutedSession:
    """Serves responses by URL fragment, so tests do not depend on request order."""

    def __init__(self, **routes):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        for fragment, response in self.routes.items():
            if fragment in url:
                return FakeGet(response)
        raise AssertionError(f"unexpected request: {url}")


def make_manager(**routes) -> tuple[EpicAPIManager, RoutedSession]:
    session = RoutedSession(**routes)
    manager = EpicAPIManager(session)  # type: ignore[arg-type]
    manager.rate_limiter = MagicMock(acquire=AsyncMock())
    return manager, session


@pytest.mark.asyncio
async def test_waf_blocked_store_page_falls_back_to_promotions():
    """The content API 404s and the store page 403s for newer products."""
    manager, _ = make_manager(
        **{
            "store-content.ak.epicgames.com": FakeResponse(404, text="not found"),
            "store.epicgames.com/en-US/p/": FakeResponse(403, text="denied"),
            "freeGamesPromotions": FakeResponse(200, payload=PROMOTIONS_PAYLOAD),
        }
    )

    details = await manager.fetch_product_details(SLUG)

    assert details is not None
    assert details["name"] == "BURIED STARS"
    assert details["is_free"] is True
    assert details["image"] == "https://cdn.example/wide.jpg"
    assert details["price_info"] == "Free to Play"
    assert details["store_url"] == f"https://store.epicgames.com/en-US/p/{SLUG}"
    assert "mystery adventure" in details["description"]


@pytest.mark.asyncio
async def test_client_rendered_store_page_falls_back_to_promotions():
    """A 200 with no og:title used to produce a details dict named "Unknown Epic Game"."""
    manager, _ = make_manager(
        **{
            "store-content.ak.epicgames.com": FakeResponse(404, text="not found"),
            "store.epicgames.com/en-US/p/": FakeResponse(200, text=JS_SHELL_HTML),
            "freeGamesPromotions": FakeResponse(200, payload=PROMOTIONS_PAYLOAD),
        }
    )

    details = await manager.fetch_product_details(SLUG)

    assert details is not None
    assert details["name"] == "BURIED STARS"
    assert UNKNOWN_EPIC_NAME not in details["name"]


@pytest.mark.asyncio
async def test_rendered_store_page_is_still_preferred():
    manager, _ = make_manager(
        **{
            "store-content.ak.epicgames.com": FakeResponse(404, text="not found"),
            "store.epicgames.com/en-US/p/": FakeResponse(200, text=RENDERED_HTML),
            "freeGamesPromotions": FakeResponse(200, payload=PROMOTIONS_PAYLOAD),
        }
    )

    details = await manager.fetch_product_details(SLUG)

    assert details is not None
    assert details["name"] == "BURIED STARS"


@pytest.mark.asyncio
async def test_unknown_product_returns_none_so_fallbacks_can_run():
    """A details dict with no name would block the ITAD and generic fallbacks upstream."""
    manager, _ = make_manager(
        **{
            "store-content.ak.epicgames.com": FakeResponse(404, text="not found"),
            "store.epicgames.com/en-US/p/": FakeResponse(200, text=JS_SHELL_HTML),
            "freeGamesPromotions": FakeResponse(200, payload={"data": {"Catalog": {"searchStore": {"elements": []}}}}),
        }
    )

    assert await manager.fetch_product_details(SLUG) is None


@pytest.mark.asyncio
async def test_promotions_slugs_cover_offer_mappings_and_home_suffixes():
    manager, _ = make_manager(
        **{"freeGamesPromotions": FakeResponse(200, payload=PROMOTIONS_PAYLOAD)},
    )
    # Replace the cache with an entry that uses an offerMappings slug and a product slug
    # still carrying the /home suffix.
    manager.free_games_cache = [
        {
            "title": "Them's Fightin' Herds",
            "productSlug": "thems-fightin-herds/home",
            "offerMappings": [{"page": {"slug": "thems-fightin-herds-offer"}}],
            "keyImages": [],
            "promotions": {"promotionalOffers": [{"promotionalOffers": []}]},
        }
    ]

    assert manager._find_promotion("thems-fightin-herds") is not None
    assert manager._find_promotion("thems-fightin-herds-offer") is not None
    assert manager._find_promotion("THEMS-FIGHTIN-HERDS") is not None
    assert manager._find_promotion("something-else") is None
    assert manager._check_is_free("thems-fightin-herds") is True
