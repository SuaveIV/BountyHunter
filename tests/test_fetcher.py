from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from bounty_core.fetcher import (
    CONTENT_BETA,
    CONTENT_DLC,
    CONTENT_GAME,
    CONTENT_ITEM,
    EpicFreeGamesFetcher,
    FreeGame,
    GamerPowerFreeGamesFetcher,
    active_epic_promotion,
    classify_content,
    classify_gamerpower_type,
    dedupe_games,
    epic_store_url,
    fetch_all_games,
    fetch_json,
    filter_games,
    is_task_exempt,
    normalize_title,
    parse_bluesky_feed,
    parse_bluesky_post,
    parse_gamerpower_giveaway,
    parse_gamerpower_giveaways,
    parse_retry_after,
    platforms_from_text,
    rejection_reason,
    requires_tasks,
    split_bluesky_title,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_game(**kwargs) -> FreeGame:
    defaults = {
        "source": "epic",
        "source_id": "1",
        "title": "Portal",
        "url": "https://store.epicgames.com/en-US/p/portal",
        "platforms": {"epic"},
        "text": "Portal is free!",
    }
    defaults.update(kwargs)
    return FreeGame(**defaults)


class StubFetcher:
    name = "stub"

    def __init__(self, games: list[FreeGame] | None = None, error: Exception | None = None):
        self.games = games or []
        self.error = error

    async def fetch_games(self) -> list[FreeGame]:
        if self.error:
            raise self.error
        return list(self.games)


# --- Model ------------------------------------------------------------------


def test_dedupe_key_is_source_scoped():
    assert make_game(source="epic", source_id="42").dedupe_key == "epic:42"
    assert make_game(source="bluesky", source_id="42").dedupe_key == "bluesky:42"


def test_title_key_strips_parentheticals_and_noise_words():
    listing = make_game(title="BURIED STARS (Epic Games) Giveaway")
    assert normalize_title(listing.title) == "buried stars"
    assert listing.title_key == "buried stars"


def test_title_key_keeps_meaningful_words():
    assert normalize_title("Portal 2") == "portal 2"
    assert normalize_title("") == ""


def test_dedupe_games_keeps_first_sighting():
    epic = make_game(source="epic", source_id="1", title="BURIED STARS (Epic Games) Giveaway")
    bluesky = make_game(source="bluesky", source_id="2", title="BURIED STARS", url="https://redd.it/abc")
    other = make_game(source="epic", source_id="3", title="Unrelated Game")

    unique = dedupe_games([epic, bluesky, other])

    assert [game.dedupe_key for game in unique] == ["epic:1", "epic:3"]


def test_dedupe_games_remembers_repeat_source_ids():
    first = make_game(source_id="1")
    second = make_game(source_id="1", title="Something else entirely")

    assert [game.source_id for game in dedupe_games([first, second])] == ["1"]


# --- Classification ---------------------------------------------------------


def test_platforms_from_text():
    assert platforms_from_text("PC, Steam") == {"steam"}
    assert platforms_from_text("Epic Games Store, Android") == {"epic"}
    assert platforms_from_text("GOG, itch.io") == {"gog", "itch"}
    assert platforms_from_text("Xbox Series X|S") == set()


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Game", CONTENT_GAME),
        ("DLC", CONTENT_DLC),
        ("Expansion", CONTENT_DLC),
        ("Season Pass", CONTENT_DLC),
        ("Beta", CONTENT_BETA),
        ("Playtest", CONTENT_BETA),
        ("Other", CONTENT_ITEM),
        ("Loot", CONTENT_ITEM),
        ("In-Game Item", CONTENT_ITEM),
        ("", CONTENT_GAME),
    ],
)
def test_classify_content(label, expected):
    assert classify_content(label) == expected


def test_classify_gamerpower_type():
    assert classify_gamerpower_type("game") == CONTENT_GAME
    assert classify_gamerpower_type("Early Access") == CONTENT_GAME
    assert classify_gamerpower_type("DLC", "Some Skin Pack") == CONTENT_DLC
    # GamerPower types loot as DLC, so the title decides when the field is vague.
    assert classify_gamerpower_type("loot", "Bonus Soundtrack") == CONTENT_ITEM


# --- Filters ----------------------------------------------------------------


def test_requires_tasks():
    assert requires_tasks("Subscribe to our newsletter for a key")
    assert requires_tasks("Complete a task to unlock")
    assert requires_tasks("Wishlist the game and leave a review")
    assert not requires_tasks("Portal is free until Friday")


def test_task_exempt_covers_gog_and_fanatical_newsletters():
    gog = make_game(
        title="Free on GOG",
        url="https://www.gog.com/game/something",
        platforms={"gog"},
        text="Subscribe to our newsletter to get this game for free",
    )
    fanatical = make_game(
        title="Fanatical giveaway",
        url="https://www.fanatical.com/en/game/foo",
        platforms={"steam"},
        text="Sign up for our newsletter",
    )
    steam = make_game(
        title="Steam giveaway",
        url="https://store.steampowered.com/app/400/",
        platforms={"steam"},
        text="Subscribe to our newsletter",
    )

    assert is_task_exempt(gog)
    assert is_task_exempt(fanatical)
    assert not is_task_exempt(steam)


def test_rejection_reason_orders_filters():
    assert rejection_reason(make_game(text="Expired giveaway")) == "excluded keyword"
    assert rejection_reason(make_game(text="Follow us on Twitter for a key")) == "requires tasks"
    assert rejection_reason(make_game(url="https://gleam.io/reward")) == "blocked domain"
    assert rejection_reason(make_game(platforms={"stove"})) == "platform not whitelisted"
    assert rejection_reason(make_game()) is None


def test_rejection_reason_steam_trust_rule_is_bluesky_only():
    untrusted = make_game(
        source="bluesky",
        platforms={"steam"},
        url="https://example.com/store",
        text="[Steam] (Game) Portal is free!",
    )
    reddit_link = make_game(
        source="bluesky",
        platforms={"steam"},
        url="https://redd.it/abc",
        text="[Steam] (Game) Portal is free!",
    )
    structured = make_game(source="gamerpower", platforms={"steam"}, url="https://example.com/store")

    assert rejection_reason(untrusted) == "untrusted steam link"
    assert rejection_reason(reddit_link) is None
    assert rejection_reason(structured) is None


def test_rejection_reason_keeps_gog_newsletter_but_drops_the_rest():
    gog = make_game(
        platforms={"gog"},
        url="https://www.gog.com/game/foo",
        text="Free game! Subscribe to our newsletter plus follow us on social media",
    )
    raffle = make_game(
        platforms={"steam"},
        url="https://example.com/giveaway",
        text="Free game! Subscribe and follow us on social media",
    )

    assert rejection_reason(gog) is None
    assert rejection_reason(raffle) == "requires tasks"


def test_filter_games_drops_and_counts():
    games = [
        make_game(source_id="1"),
        make_game(source_id="2", text="Raffle!"),
        make_game(source_id="3", platforms=set()),
    ]

    accepted = filter_games(games)

    assert [game.source_id for game in accepted] == ["1"]


# --- Fake HTTP --------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int, payload=None, headers: dict[str, str] | None = None):
        self.status = status
        self.payload = payload
        self.headers = headers or {}

    async def json(self, content_type=None):
        return self.payload


class FakeGet:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    """Minimal aiohttp.ClientSession stand-in that replays queued responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeGet(self.responses.pop(0))


# --- Epic -------------------------------------------------------------------

EPIC_ELEMENT = {
    "id": "abc123",
    "title": "BURIED STARS",
    "description": "A visual novel.",
    "offerMappings": [{"page": {"slug": "buried-stars"}}],
    "promotions": {
        "promotionalOffers": [
            {
                "promotionalOffers": [
                    {
                        "startDate": "2025-12-20T15:00:00.000Z",
                        "endDate": "2026-01-03T15:00:00.000Z",
                        "discountSetting": {"discountPercentage": 0},
                    }
                ]
            }
        ]
    },
}


def test_active_epic_promotion_window():
    assert active_epic_promotion(EPIC_ELEMENT, NOW) is not None
    assert active_epic_promotion(EPIC_ELEMENT, datetime(2025, 1, 1, tzinfo=UTC)) is None
    assert active_epic_promotion(EPIC_ELEMENT, datetime(2027, 1, 1, tzinfo=UTC)) is None


def test_active_epic_promotion_ignores_discounted_and_missing_offers():
    discounted = {
        "promotions": {
            "promotionalOffers": [
                {
                    "promotionalOffers": [
                        {"discountSetting": {"discountPercentage": 50}, "startDate": "2025-12-20T15:00:00Z"}
                    ]
                }
            ]
        }
    }
    assert active_epic_promotion(discounted, NOW) is None
    assert active_epic_promotion({"promotions": {}}, NOW) is None


def test_epic_store_url_variants():
    assert epic_store_url(EPIC_ELEMENT) == "https://store.epicgames.com/en-US/p/buried-stars"
    assert epic_store_url({"productSlug": "some-game/home"}) == "https://store.epicgames.com/en-US/p/some-game"
    assert epic_store_url({"urlSlug": "other-game"}) == "https://store.epicgames.com/en-US/p/other-game"
    assert epic_store_url({}) is None


@pytest.mark.asyncio
async def test_epic_fetcher_returns_free_games_only():
    payload = {"data": {"Catalog": {"searchStore": {"elements": [EPIC_ELEMENT, {"id": "not-free"}]}}}}
    session = FakeSession(FakeResponse(200, payload))

    games = await EpicFreeGamesFetcher(session).fetch_games(now=NOW)

    assert len(games) == 1
    game = games[0]
    assert game.source == "epic"
    assert game.source_id == "abc123"
    assert game.url == "https://store.epicgames.com/en-US/p/buried-stars"
    assert game.platforms == {"epic"}
    assert game.content_type == CONTENT_GAME
    assert game.expires_at == "2026-01-03T15:00:00.000Z"
    assert "A visual novel." in game.text


@pytest.mark.asyncio
async def test_epic_fetcher_survives_bad_payloads():
    session = FakeSession(FakeResponse(200, {}), FakeResponse(404), FakeResponse(200, "nonsense"))
    fetcher = EpicFreeGamesFetcher(session)

    assert await fetcher.fetch_games(now=NOW) == []
    assert await fetcher.fetch_games(now=NOW) == []
    assert await fetcher.fetch_games(now=NOW) == []


# --- GamerPower -------------------------------------------------------------

GAMERPOWER_GAME = {
    "id": 1234,
    "title": "Some Free Game",
    "description": "A description",
    "instructions": "Redeem on Steam",
    "status": "active",
    "type": "game",
    "platforms": "PC, Steam",
    "end_date": "2026-02-01 23:59:00",
    "open_giveaway_url": "https://www.gamerpower.com/open/some-free-game",
}


def test_parse_gamerpower_giveaway():
    game = parse_gamerpower_giveaway(GAMERPOWER_GAME)

    assert game is not None
    assert game.source == "gamerpower"
    assert game.source_id == "1234"
    assert game.platforms == {"steam"}
    assert game.content_type == CONTENT_GAME
    assert game.expires_at == "2026-02-01 23:59:00"
    assert "Redeem on Steam" in game.text


def test_parse_gamerpower_giveaway_filters_and_fallbacks():
    assert parse_gamerpower_giveaway({**GAMERPOWER_GAME, "status": "expired"}) is None
    assert parse_gamerpower_giveaway({**GAMERPOWER_GAME, "status": "Active"}) is not None

    no_open_url = {**GAMERPOWER_GAME, "open_giveaway_url": "", "open_giveaway": "https://x.example/game"}
    assert parse_gamerpower_giveaway(no_open_url).url == "https://x.example/game"

    no_end_date = {**GAMERPOWER_GAME, "end_date": "N/A"}
    assert parse_gamerpower_giveaway(no_end_date).expires_at is None

    loot = {**GAMERPOWER_GAME, "type": "loot", "title": "Bonus Soundtrack", "platforms": "PC, GOG"}
    assert parse_gamerpower_giveaway(loot).content_type == CONTENT_ITEM
    assert parse_gamerpower_giveaway(loot).platforms == {"gog"}


def test_parse_gamerpower_giveaways_handles_non_list_payloads():
    assert parse_gamerpower_giveaways({"error": "No object found"}) == []
    assert len(parse_gamerpower_giveaways([GAMERPOWER_GAME, "junk", {}])) == 1


@pytest.mark.asyncio
async def test_gamerpower_fetcher_queries_game_and_loot_separately():
    session = FakeSession(FakeResponse(200, [GAMERPOWER_GAME]), FakeResponse(200, []))
    fetcher = GamerPowerFreeGamesFetcher(session)

    games = await fetcher.fetch_games()

    assert [game.source_id for game in games] == ["1234"]
    assert [call[1]["params"]["type"] for call in session.calls] == ["game", "loot"]


# --- Bluesky ----------------------------------------------------------------

BLUESKY_FEED = {
    "feed": [
        {
            "post": {
                "uri": "at://did:plc:abc/app.bsky.feed.post/3kabc",
                "record": {
                    "text": "[Steam] (DLC) Blair Witch bonus content is free! https://redd.it/1abc?utm_source=bsky",
                    "facets": [
                        {
                            "features": [
                                {"$type": "app.bsky.richtext.facet#link", "uri": "https://redd.it/1abc?utm_source=bsky"}
                            ]
                        }
                    ],
                },
            }
        },
        {
            "post": {
                "uri": "at://did:plc:abc/app.bsky.feed.post/3kreply",
                "record": {"text": "[Steam] (Game) A reply", "reply": {"parent": {"uri": "at://x"}}},
            }
        },
        {"post": {"uri": "at://did:plc:abc/app.bsky.feed.post/3kempty", "record": {"text": "   "}}},
        "junk",
    ]
}


def test_parse_bluesky_feed_strips_tags_and_replies():
    games = parse_bluesky_feed(BLUESKY_FEED)

    assert len(games) == 1
    game = games[0]
    assert game.source == "bluesky"
    assert game.source_id == "at://did:plc:abc/app.bsky.feed.post/3kabc"
    assert game.title == "Blair Witch bonus content"
    assert game.platforms == {"steam"}
    assert game.content_type == CONTENT_DLC
    # Query strings are stripped, and the raw post text is kept for keyword filters.
    assert game.url == "https://redd.it/1abc"
    assert "utm_source" not in game.url
    assert game.text.startswith("[Steam] (DLC)")


def test_parse_bluesky_feed_handles_bad_payloads():
    assert parse_bluesky_feed(None) == []
    assert parse_bluesky_feed({"feed": []}) == []


def test_split_bluesky_title_strips_boilerplate_for_cross_source_dedupe():
    platform_tag, content_tag, title = split_bluesky_title(
        "[Steam] (Game) Blair Witch is free! See the /r/FreeGameFindings thread below."
    )
    assert (platform_tag, content_tag, title) == ("Steam", "Game", "Blair Witch")

    # Title keys then collapse the same game posted by another source.
    bluesky = make_game(source="bluesky", source_id="1", title=title)
    gamerpower = make_game(source="gamerpower", source_id="2", title="Blair Witch (Steam) Giveaway")
    assert bluesky.title_key == gamerpower.title_key

    assert split_bluesky_title("(DLC) Everwind - AW-51 Pack are free!")[2] == "Everwind - AW-51 Pack"
    assert split_bluesky_title("[Steam] (Game)   ")[2] == ""


def test_parse_bluesky_feed_falls_back_to_body_link_then_permalink():
    body_link = parse_bluesky_post(
        {
            "post": {
                "uri": "at://did:plc:abc/app.bsky.feed.post/2",
                "record": {"text": "[GOG] (Game) Syndicate is free! https://www.gog.com/game/syndicate."},
            }
        }
    )
    assert body_link.url == "https://www.gog.com/game/syndicate"
    assert body_link.platforms == {"gog"}
    assert body_link.content_type == CONTENT_GAME

    permalink = parse_bluesky_post(
        {"post": {"uri": "at://did:plc:abc/app.bsky.feed.post/3", "record": {"text": "[Epic] (Game) Some game"}}}
    )
    assert permalink.url == "https://bsky.app/profile/freegamefindings.bsky.social/post/3"


# --- HTTP -------------------------------------------------------------------


def test_parse_retry_after_accepts_seconds_and_http_dates():
    assert parse_retry_after("5") == 5.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("nonsense") is None

    future = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    parsed = parse_retry_after(future.strftime("%a, %d %b %Y %H:%M:%S GMT"))
    assert parsed is not None and 25 <= parsed <= 31

    past = datetime.now(UTC) - timedelta(seconds=30)
    assert parse_retry_after(past.strftime("%a, %d %b %Y %H:%M:%S GMT")) == 0.0


@pytest.mark.asyncio
async def test_fetch_json_retries_transient_statuses():
    session = FakeSession(FakeResponse(503), FakeResponse(200, {"ok": True}))

    with patch("bounty_core.fetcher.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        payload = await fetch_json(session, "https://example.com/api")

    assert payload == {"ok": True}
    assert len(session.calls) == 2
    mock_sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_json_honours_retry_after():
    session = FakeSession(FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, {"ok": True}))

    with patch("bounty_core.fetcher.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        assert await fetch_json(session, "https://example.com/api") == {"ok": True}

    mock_sleep.assert_awaited_once_with(7.0)


@pytest.mark.asyncio
async def test_fetch_json_gives_up_on_permanent_failures():
    session = FakeSession(FakeResponse(404))

    assert await fetch_json(session, "https://example.com/api") is None
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_fetch_json_gives_up_after_max_retries():
    session = FakeSession(*[FakeResponse(502) for _ in range(5)])

    with patch("bounty_core.fetcher.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        assert await fetch_json(session, "https://example.com/api") is None

    # 1 attempt + MAX_RETRIES retries
    assert len(session.calls) == 4
    assert mock_sleep.await_count == 3


@pytest.mark.asyncio
async def test_fetch_json_retries_network_errors():
    session = FakeSession(FakeResponse(200, {"ok": True}))
    original_get = session.get
    calls = {"count": 0}

    def flaky_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise aiohttp.ClientError("connection reset")
        return original_get(url, **kwargs)

    session.get = flaky_get

    with patch("bounty_core.fetcher.asyncio.sleep", new=AsyncMock()):
        assert await fetch_json(session, "https://example.com/api") == {"ok": True}

    assert calls["count"] == 2


# --- Fan-in -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_all_games_skips_failing_fetchers_and_keeps_order():
    epic = StubFetcher([make_game(source="epic", source_id="1", title="Epic Game")])
    broken = StubFetcher(error=RuntimeError("403 from the feed"))
    bluesky = StubFetcher([make_game(source="bluesky", source_id="2", title="Bluesky Game")])

    games = await fetch_all_games([epic, broken, bluesky])

    assert [(game.source, game.source_id) for game in games] == [("epic", "1"), ("bluesky", "2")]
