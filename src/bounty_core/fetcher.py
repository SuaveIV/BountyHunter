"""
Feed fetchers for BountyHunter.

Every fetcher returns a normalized :class:`FreeGame`, so the scanner can fan several
independent sources in and treat a single dead feed as a skipped source instead of a
failed scan.

Sources (all keyless):

* :class:`RedditRSSFetcher` - the original r/FreeGameFindings RSS scrape. Reddit is
  retiring RSS (Nov 2026) and public API access (Mar 2027), and the feed already 403s, so
  it is no longer wired into the scanner. It is deliberately kept until Reddit fully pulls
  the plug rather than deleted: the fan-in only takes fetchers that return normalized
  listings, and this one still returns raw feed dicts, so re-enabling it means adapting it
  to :class:`FreeGamesFetcher` and adding it to :data:`DEFAULT_FETCHERS`.
* :class:`EpicFreeGamesFetcher` - Epic's public ``freeGamesPromotions`` endpoint. Gives
  direct store links.
* :class:`GamerPowerFreeGamesFetcher` - GamerPower's ``giveaways`` API, queried once for
  ``game`` and once for ``loot`` (the API rejects multi-type queries and 404s on
  ``dlc``/``beta``).
* :class:`BlueskyFreeGamesFetcher` - the r/FreeGameFindings Bluesky mirror, kept as a
  resilience backstop since that account is itself a bot mirroring the subreddit.

Deduplication happens in two dimensions: ``dedupe_key`` remembers individual listings
across runs, while ``title_key`` collapses the same game posted by several sources onto a
single title. Fetchers are ordered Epic -> GamerPower -> Bluesky because dedupe keeps the
first sighting, which puts the authoritative, direct-link sources ahead of Bluesky's
Reddit-thread links.
"""

import asyncio
import logging
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from bounty_core.constants import DENY_DOMAINS
from bounty_core.network import HEADERS
from bounty_core.parser import normalize_title
from bounty_core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

FEED_URL = "https://www.reddit.com/r/FreeGameFindings/new/.rss"
MAX_RETRIES = 3
BASE_DELAY = 2.0
TARGET_ACTOR = "r/FreeGameFindings"


class RedditRSSFetcher:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_latest(self, limit: int = 10) -> list[dict[str, Any]]:
        # Merge our specific User-Agent with the standard headers if we want to identify the bot
        # But generally, for scraping, looking like a browser is safer.
        # We'll stick to the standard browser headers for now to avoid blocks.
        request_headers = HEADERS.copy()

        for attempt in range(MAX_RETRIES):
            try:
                # We fetch the content as text first, then pass to feedparser
                # feedparser can fetch URL directly, but using aiohttp keeps it async
                async with self.session.get(FEED_URL, headers=request_headers) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        # feedparser.parse can take a string
                        feed = feedparser.parse(content)

                        posts = []
                        for entry in feed.entries[:limit]:
                            post = self._parse_entry(entry)
                            if post:
                                posts.append(post)
                        return posts

                    if resp.status == 429 or 500 <= resp.status < 600:
                        delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # nosec B311
                        logger.warning(f"Reddit RSS fetch failed ({resp.status}). Retrying in {delay:.2f}s...")
                        await asyncio.sleep(delay)
                        continue

                    logger.error(f"Reddit RSS fetch failed: {resp.status}")
                    return []
            except Exception as e:
                delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # nosec B311
                logger.error(f"Exception fetching Reddit RSS: {e}. Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

        logger.error("Max retries exceeded for Reddit RSS fetcher.")
        return []

    def _parse_entry(self, entry: Any) -> dict[str, Any] | None:
        try:
            # Basic Fields
            title = entry.get("title", "No Title")
            reddit_link = entry.get("link", "")
            reddit_id = entry.get("id", reddit_link)

            # Content Parsing for External Link and Thumbnail
            content_html = ""
            if "content" in entry:
                content_html = entry.content[0].value
            elif "description" in entry:
                content_html = entry.description

            soup = BeautifulSoup(content_html, "html.parser")

            # Extract External Link
            # r/FreeGameFindings usually has a link with text "[link]"
            external_link = None
            link_tag = None
            for a in soup.find_all("a"):
                if a.string == "[link]":
                    link_tag = a
                    break

            if link_tag and link_tag.has_attr("href"):
                external_link = link_tag["href"]
            else:
                # Fallback: find the first link that isn't a reddit link
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "reddit.com" not in href and "redd.it" not in href:
                        external_link = href
                        break

            # If no external link found, use the reddit link (it might be a discussion post)
            if not external_link:
                external_link = reddit_link

            # Extract Thumbnail
            thumbnail = None
            # Check media_thumbnail (feedparser specific)
            if "media_thumbnail" in entry and entry.media_thumbnail:
                thumbnail = entry.media_thumbnail[0]["url"]
            # Fallback to looking for img in content
            if not thumbnail:
                img = soup.find("img")
                if img and img.has_attr("src"):
                    thumbnail = img["src"]

            return {
                "id": reddit_id,
                "title": title,
                "url": reddit_link,  # The Reddit Post URL
                "external_url": external_link,  # The Deal URL
                "thumbnail": thumbnail,
                "date": entry.get("updated") or entry.get("published"),
            }

        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None


# --- Source identifiers -----------------------------------------------------

SOURCE_EPIC = "epic"
SOURCE_GAMERPOWER = "gamerpower"
SOURCE_BLUESKY = "bluesky"

#: Human readable labels, used for embed footers and log lines.
SOURCE_LABELS = {
    SOURCE_EPIC: "Epic Games Store",
    SOURCE_GAMERPOWER: "GamerPower",
    SOURCE_BLUESKY: "Bluesky (r/FreeGameFindings)",
}

# --- Content types ----------------------------------------------------------

CONTENT_GAME = "game"
CONTENT_DLC = "dlc"
CONTENT_ITEM = "item"
CONTENT_BETA = "beta"

CONTENT_LABELS = {
    CONTENT_GAME: "FREE GAME",
    CONTENT_DLC: "FREE DLC",
    CONTENT_ITEM: "FREE ITEM",
    CONTENT_BETA: "FREE BETA",
}

#: Every content type the fetchers can report.
CONTENT_TYPES = frozenset({CONTENT_GAME, CONTENT_DLC, CONTENT_ITEM, CONTENT_BETA})

#: Games only. GamerPower alone returns roughly three DLC or item giveaways for every game,
#: which fills a channel faster than anyone wants to read it.
DEFAULT_CONTENT_TYPES = frozenset({CONTENT_GAME})

#: Spellings accepted in the content-type setting.
CONTENT_TYPE_ALIASES = {
    "game": CONTENT_GAME,
    "games": CONTENT_GAME,
    "dlc": CONTENT_DLC,
    "dlcs": CONTENT_DLC,
    "addon": CONTENT_DLC,
    "addons": CONTENT_DLC,
    "expansion": CONTENT_DLC,
    "expansion pass": CONTENT_DLC,
    "item": CONTENT_ITEM,
    "items": CONTENT_ITEM,
    "loot": CONTENT_ITEM,
    "beta": CONTENT_BETA,
    "betas": CONTENT_BETA,
    "playtest": CONTENT_BETA,
}


def parse_content_types(value: str | None) -> frozenset[str]:
    """
    Parse a comma separated content-type setting, e.g. ``game,dlc``.

    Unrecognised entries are logged and ignored, and a setting that names no known type
    falls back to games rather than silently muting the channel.
    """
    if not value or not value.strip():
        return DEFAULT_CONTENT_TYPES

    requested = [token.strip().lower() for token in value.split(",") if token.strip()]
    known = {CONTENT_TYPE_ALIASES[token] for token in requested if token in CONTENT_TYPE_ALIASES}
    unknown = [token for token in requested if token not in CONTENT_TYPE_ALIASES]

    if unknown:
        logger.warning(f"Ignoring unknown content type(s) in configuration: {', '.join(unknown)}")

    return frozenset(known) or DEFAULT_CONTENT_TYPES


# --- Platform tokens --------------------------------------------------------

PLATFORM_STEAM = "steam"
PLATFORM_EPIC = "epic"
PLATFORM_AMAZON = "amazon"
PLATFORM_GOG = "gog"
PLATFORM_ITCH = "itch"

#: Only listings that can be claimed on one of these stores are interesting.
PLATFORM_TOKENS = frozenset({PLATFORM_STEAM, PLATFORM_EPIC, PLATFORM_AMAZON, PLATFORM_GOG, PLATFORM_ITCH})

#: Substring -> platform token. Used for GamerPower's comma separated platform strings and
#: for Bluesky's leading ``[Steam]`` style tags.
PLATFORM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("steam", PLATFORM_STEAM),
    ("epic", PLATFORM_EPIC),
    ("amazon", PLATFORM_AMAZON),
    ("prime gaming", PLATFORM_AMAZON),
    ("prime", PLATFORM_AMAZON),
    ("gog", PLATFORM_GOG),
    ("itch", PLATFORM_ITCH),
)

# --- HTTP tuning ------------------------------------------------------------

DEFAULT_FETCH_INTERVAL = 1.0
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
MAX_JITTER_SECONDS = 1.0


@dataclass
class FreeGame:
    """A normalized free-game listing, as returned by every fetcher."""

    source: str
    source_id: str
    title: str
    url: str
    platforms: set[str] = field(default_factory=set)
    text: str = ""
    expires_at: str | None = None
    content_type: str = CONTENT_GAME

    @property
    def dedupe_key(self) -> str:
        """Stable per-source key; remembers a listing across runs."""
        return f"{self.source}:{self.source_id}"

    @property
    def title_key(self) -> str:
        """Cross-source key; collapses the same game posted by several sources."""
        return normalize_title(self.title)


# Noise words stripped from titles before cross-source comparison live in
# :mod:`bounty_core.parser` (see ``normalize_title``), alongside the other text heuristics.


def dedupe_games(games: Sequence[FreeGame]) -> list[FreeGame]:
    """
    Drop repeat sightings, keeping the first occurrence.

    Games are expected to arrive in fetcher-priority order (Epic, GamerPower, Bluesky), so
    "first wins" prefers the source with a direct store link.
    """
    seen_keys: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[FreeGame] = []

    for game in games:
        if game.dedupe_key in seen_keys:
            continue
        seen_keys.add(game.dedupe_key)

        title_key = game.title_key
        if title_key and title_key in seen_titles:
            logger.debug("Deduped '%s' from %s against an earlier listing", game.title, game.source)
            continue
        if title_key:
            seen_titles.add(title_key)

        unique.append(game)

    return unique


# --- HTTP -------------------------------------------------------------------


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header, accepting both the delay and HTTP-date forms."""
    if not value:
        return None

    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with a little jitter, capped at :data:`MAX_BACKOFF_SECONDS`."""
    delay: float = min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * (2**attempt))
    return delay + random.uniform(0, MAX_JITTER_SECONDS)  # nosec B311


async def handle_api_response(response: aiohttp.ClientResponse) -> Any | None:
    """Parse a JSON body, tolerating servers that mislabel their content type."""
    try:
        return await response.json(content_type=None)
    except (aiohttp.ClientError, ValueError, TypeError) as e:
        logger.warning(f"Malformed JSON from {response.url}: {e}")
        return None


async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    limiter: RateLimiter | None = None,
    retries: int = MAX_RETRIES,
) -> Any | None:
    """
    Fetch JSON with per-fetcher spacing (:class:`RateLimiter`) and retry handling.

    ``429``/``5xx`` and connection errors are retried, honouring ``Retry-After`` when the
    server sends one and falling back to exponential backoff otherwise. Any other non-200
    status is treated as permanent and gives up immediately. Returns ``None`` when the
    request ultimately fails, so one dead feed cannot take the whole scan down.

    Note: Steam store requests are deliberately not routed through here; they go through
    :class:`~bounty_core.steam_api_manager.SteamAPIManager`, which has its own interval
    limiter and 429 handling.
    """
    for attempt in range(retries + 1):
        if limiter is not None:
            await limiter.acquire()

        try:
            async with session.get(url, params=params, headers=HEADERS) as response:
                if response.status == 200:
                    return await handle_api_response(response)

                if response.status in RETRYABLE_STATUSES:
                    if attempt >= retries:
                        logger.error(f"{url} kept returning {response.status}; giving up")
                        return None
                    delay = parse_retry_after(response.headers.get("Retry-After"))
                    if delay is None:
                        delay = backoff_delay(attempt)
                    logger.warning(f"{url} returned {response.status}; retrying in {delay:.2f}s")
                    await asyncio.sleep(delay)
                    continue

                logger.warning(f"Request to {url} failed with status {response.status}")
                return None
        except (aiohttp.ClientError, TimeoutError) as e:
            if attempt >= retries:
                logger.error(f"Network error fetching {url}; giving up: {e}")
                return None
            delay = backoff_delay(attempt)
            logger.warning(f"Network error fetching {url} ({e}); retrying in {delay:.2f}s")
            await asyncio.sleep(delay)

    return None


def parse_iso_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp as returned by the Epic API."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


# --- Classification ---------------------------------------------------------


def platforms_from_text(value: str) -> set[str]:
    """Map a free-form platform string ("PC, Steam") onto platform tokens."""
    lowered = (value or "").lower()
    return {token for pattern, token in PLATFORM_PATTERNS if pattern in lowered}


CONTENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (CONTENT_DLC, ("dlc", "addon", "add-on", "expansion", "season pass")),
    (CONTENT_BETA, ("beta", "playtest")),
    (CONTENT_ITEM, ("loot", "item", "other", "in-game", "avatar", "skin")),
)

#: GamerPower's ``type`` field, mapped onto our content types.
GAMERPOWER_TYPE_ALIASES = {
    "game": CONTENT_GAME,
    "early access": CONTENT_GAME,
    "dlc": CONTENT_DLC,
    "loot": CONTENT_ITEM,
    "beta": CONTENT_BETA,
    "demo": CONTENT_BETA,
}


def classify_content(label: str) -> str:
    """Map an FGF-style "(Game)"/"(DLC)"/"(Other)" marker to a content type."""
    lowered = (label or "").strip().lower()
    for content_type, patterns in CONTENT_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return content_type
    return CONTENT_GAME


def classify_gamerpower_type(raw_type: str, title: str = "") -> str:
    """
    Map GamerPower's ``type`` field onto a content type.

    GamerPower types ``loot`` entries as DLC when it can, but the field is unreliable for
    bundles, so the title is checked too before trusting ``loot``.
    """
    lowered = (raw_type or "").strip().lower()
    mapped = GAMERPOWER_TYPE_ALIASES.get(lowered)

    if mapped == CONTENT_GAME:
        return CONTENT_GAME
    if mapped:
        return classify_content(f"{mapped} {title}")
    return classify_content(f"{lowered} {title}")


# --- Filtering --------------------------------------------------------------

EXCLUDED_KEYWORDS = ("expired", "raffle", "sweepstake")

#: FGF's weekly thread and its themed "mega threads" ("Exiled Giveaways and Itch.io Mega
#: Threads") collect a pile of giveaways in one post. They are not listings: they carry no
#: platform tag, their body links to every store going, so resolving one announces whichever
#: game happened to be linked first.
AGGREGATE_THREAD_PHRASES = (
    "weekly thread",
    "weekly discussion",
    "weekly roundup",
    "giveaway thread",
    "giveaways thread",
    "mega giveaway thread",
    "giveaway mega thread",
    "mega thread",
    "mega threads",
    "megathread",
)

TASK_KEYWORDS = (
    "newsletter",
    "subscribe",
    "subscription",
    "follow us",
    "follow our",
    "follow on",
    "following us",
    "retweet",
    "repost",
    "share the",
    "survey",
    "complete a task",
    "complete tasks",
    "points required",
    "arp required",
    "reach level",
    "level up",
    "invite friends",
    "refer a friend",
    "gleam",
    "givee.club",
    "woovit",
    "keymailer",
    "watch a video",
    "join our discord",
    "daily check",
    "check-in",
    "leave a review",
    "leave a comment",
    "wishlist our",
    "wishlist the",
)

NEWSLETTER_KEYWORDS = ("newsletter", "subscribe", "subscription")

#: Task requirements that need a pattern rather than a phrase. Alienware Arena asks for
#: "5 ARP (Alienware Rewards Points) to claim a key", which the keyword list let through.
TASK_PATTERNS = (
    re.compile(r"\b\d*\s*arp\b", re.IGNORECASE),
    re.compile(r"\d+\s*rewards? points\b", re.IGNORECASE),
)

#: Bluesky posts are unstructured, so a Steam-tagged post only counts when it links
#: somewhere we can verify. Structured fetchers carry clean links, so they are trusted.
TRUSTED_STEAM_HOSTS = ("store.steampowered.com", "redd.it", "reddit.com")


def match_keywords(text: str, keywords: Sequence[str]) -> set[str]:
    """Return the subset of ``keywords`` present in ``text`` (case-insensitive)."""
    lowered = (text or "").lower()
    return {keyword for keyword in keywords if keyword in lowered}


def requires_tasks(text: str) -> bool:
    """True when the listing asks the user to complete a task (follow, subscribe, ...)."""
    if match_keywords(text, TASK_KEYWORDS):
        return True

    return any(pattern.search(text or "") for pattern in TASK_PATTERNS)


def is_aggregate_thread(text: str) -> bool:
    """True for FGF weekly/mega threads, which aggregate giveaways instead of being one."""
    normalized = re.sub(r"[_\-]+", " ", (text or "").lower())
    return any(phrase in normalized for phrase in AGGREGATE_THREAD_PHRASES)


def is_task_exempt(game: FreeGame) -> bool:
    """
    Newsletter giveaways from GOG and Fanatical are allowed through.

    They technically "require tasks", but the task is a newsletter signup rather than a
    raffle, which is the usual intent of the keyword filter.
    """
    matched = match_keywords(game.text, TASK_KEYWORDS)
    if not matched & set(NEWSLETTER_KEYWORDS):
        return False

    if PLATFORM_GOG in game.platforms or "gog.com" in game.url.lower():
        return True

    haystack = f"{game.title}\n{game.text}\n{game.url}".lower()
    return "fanatical" in haystack


def rejection_reason(game: FreeGame, allowed_content_types: frozenset[str] | None = None) -> str | None:
    """
    Explain why a listing should be dropped, or ``None`` when it should be announced.

    Filtering runs in order: aggregate threads, content type, excluded keywords, task
    giveaways, blocked domains, the platform whitelist, and finally the Bluesky Steam trust
    rule. The whitelist is what drops the mobile, STOVE, VR and DRM-free-only listings
    GamerPower returns.

    ``allowed_content_types`` is the caller's policy, read from configuration by the Discord
    layer. ``None`` keeps every content type, which is what the core does by default.
    """
    text = game.text or ""
    lowered_text = text.lower()

    if is_aggregate_thread(game.title) or is_aggregate_thread(game.url):
        return "aggregate thread"

    if allowed_content_types is not None and game.content_type not in allowed_content_types:
        return "content type not enabled"

    if any(keyword in lowered_text for keyword in EXCLUDED_KEYWORDS):
        return "excluded keyword"

    if requires_tasks(text) and not is_task_exempt(game):
        return "requires tasks"

    haystack = f"{game.url.lower()}\n{lowered_text}"
    if any(domain in haystack for domain in DENY_DOMAINS):
        return "blocked domain"

    if not game.platforms & PLATFORM_TOKENS:
        return "platform not whitelisted"

    if game.source == SOURCE_BLUESKY and PLATFORM_STEAM in game.platforms:
        if not any(host in game.url.lower() for host in TRUSTED_STEAM_HOSTS):
            return "untrusted steam link"

    return None


def filter_games(games: Sequence[FreeGame], allowed_content_types: frozenset[str] | None = None) -> list[FreeGame]:
    """Apply :func:`rejection_reason` to every game and log a per-reason summary."""
    accepted: list[FreeGame] = []
    skipped: dict[str, int] = {}

    for game in games:
        reason = rejection_reason(game, allowed_content_types)
        if reason is None:
            accepted.append(game)
        else:
            skipped[reason] = skipped.get(reason, 0) + 1
            logger.debug(f"Filtered '{game.title}' from {game.source}: {reason}")

    if skipped:
        summary = ", ".join(f"{reason}={count}" for reason, count in sorted(skipped.items()))
        logger.info(f"Filtered {len(games) - len(accepted)}/{len(games)} listings ({summary})")

    return accepted


# --- Epic -------------------------------------------------------------------

EPIC_PROMOTIONS_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
EPIC_PROMOTIONS_PARAMS = {"locale": "en-US", "country": "US", "allowCountries": "US"}


def active_epic_promotion(element: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    """Return the currently running 0%-discount promotion for an Epic catalog element."""
    groups = (element.get("promotions") or {}).get("promotionalOffers") or []

    for group in groups:
        for offer in (group or {}).get("promotionalOffers") or []:
            discount = (offer.get("discountSetting") or {}).get("discountPercentage")
            if str(discount) != "0":
                continue

            start = parse_iso_timestamp(offer.get("startDate"))
            end = parse_iso_timestamp(offer.get("endDate"))
            if start and now < start:
                continue
            if end and now > end:
                continue

            return offer

    return None


def epic_store_url(element: dict[str, Any]) -> str | None:
    """Build the canonical store URL for an Epic catalog element."""
    slug = None
    for mapping in element.get("offerMappings") or []:
        page = (mapping or {}).get("page") or {}
        if page.get("slug"):
            slug = str(page["slug"])
            break

    if not slug:
        raw_slug = element.get("productSlug") or element.get("urlSlug")
        if raw_slug:
            slug = str(raw_slug).removesuffix("/home")

    if not slug:
        return None

    return f"https://store.epicgames.com/en-US/p/{slug.strip('/')}"


class EpicFreeGamesFetcher:
    """Epic's public free-games promotions endpoint. Keyless, and links straight to the store."""

    name = SOURCE_EPIC

    def __init__(self, session: aiohttp.ClientSession, interval: float = DEFAULT_FETCH_INTERVAL):
        self.session = session
        self.rate_limiter = RateLimiter(calls_per_second=1.0 / interval)

    async def fetch_games(self, now: datetime | None = None) -> list[FreeGame]:
        payload = await fetch_json(
            self.session,
            EPIC_PROMOTIONS_URL,
            params=EPIC_PROMOTIONS_PARAMS,
            limiter=self.rate_limiter,
        )
        if not isinstance(payload, dict):
            return []

        elements = (payload.get("data") or {}).get("Catalog", {}).get("searchStore", {}).get("elements") or []
        moment = now or datetime.now(UTC)
        games: list[FreeGame] = []

        for element in elements:
            if not isinstance(element, dict):
                continue

            offer = active_epic_promotion(element, moment)
            if not offer:
                continue

            url = epic_store_url(element)
            title = str(element.get("title") or "").strip()
            if not url or not title:
                continue

            description = str(element.get("description") or "").strip()
            games.append(
                FreeGame(
                    source=SOURCE_EPIC,
                    source_id=str(element.get("id") or url),
                    title=title,
                    url=url,
                    platforms={PLATFORM_EPIC},
                    text="\n".join(part for part in (title, description) if part),
                    expires_at=offer.get("endDate"),
                    content_type=CONTENT_GAME,
                )
            )

        return games


# --- GamerPower -------------------------------------------------------------

GAMERPOWER_API_URL = "https://www.gamerpower.com/api/giveaways"

#: GamerPower rejects multi-type queries (``type=game+loot``, ``type=game%2Bloot`` and
#: ``type=game,loot`` all return "No object found") and 404s on ``dlc``/``beta``, so the
#: two interesting types are queried separately.
GAMERPOWER_QUERY_TYPES = ("game", "loot")
GAMERPOWER_NA_VALUES = frozenset({"", "n/a", "none", "unknown"})


def parse_gamerpower_giveaway(entry: dict[str, Any]) -> FreeGame | None:
    """Normalize a single GamerPower giveaway entry."""
    if str(entry.get("status") or "").strip().lower() != "active":
        return None

    title = str(entry.get("title") or "").strip()
    url = str(entry.get("open_giveaway_url") or entry.get("open_giveaway") or "").strip()
    if not title or not url:
        return None

    description = str(entry.get("description") or "").strip()
    instructions = str(entry.get("instructions") or "").strip()
    end_date = str(entry.get("end_date") or "").strip()

    return FreeGame(
        source=SOURCE_GAMERPOWER,
        source_id=str(entry.get("id") or url),
        title=title,
        url=url,
        platforms=platforms_from_text(str(entry.get("platforms") or "")),
        text="\n".join(part for part in (title, description, instructions) if part),
        expires_at=None if end_date.lower() in GAMERPOWER_NA_VALUES else end_date,
        content_type=classify_gamerpower_type(str(entry.get("type") or ""), title),
    )


def parse_gamerpower_giveaways(payload: Any) -> list[FreeGame]:
    """Normalize a GamerPower response, which is a bare JSON list."""
    if not isinstance(payload, list):
        return []

    games: list[FreeGame] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        game = parse_gamerpower_giveaway(entry)
        if game:
            games.append(game)
    return games


class GamerPowerFreeGamesFetcher:
    """GamerPower's giveaways API. Their terms require attribution and cap at 10 req/s."""

    name = SOURCE_GAMERPOWER

    def __init__(self, session: aiohttp.ClientSession, interval: float = DEFAULT_FETCH_INTERVAL):
        self.session = session
        self.rate_limiter = RateLimiter(calls_per_second=1.0 / interval)

    async def fetch_games(self) -> list[FreeGame]:
        games: list[FreeGame] = []
        for query_type in GAMERPOWER_QUERY_TYPES:
            payload = await fetch_json(
                self.session,
                GAMERPOWER_API_URL,
                params={"type": query_type},
                limiter=self.rate_limiter,
            )
            games.extend(parse_gamerpower_giveaways(payload))
        return games


# --- Bluesky ----------------------------------------------------------------

BLUESKY_FEED_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
BLUESKY_ACTOR = "freegamefindings.bsky.social"
BLUESKY_FEED_LIMIT = 20
BLUESKY_LINK_FEATURE = "app.bsky.richtext.facet#link"

BLUESKY_PLATFORM_TAG_REGEX = re.compile(r"^\s*\[([^\]]{1,40})\]\s*")
BLUESKY_CONTENT_TAG_REGEX = re.compile(r"^\s*\(([^)]{1,40})\)\s*")
BLUESKY_URL_REGEX = re.compile(r"https?://[^\s\)\]<>]+")

#: The mirror appends these to every post; they would otherwise defeat cross-source
#: title dedupe ("Blair Witch is free! See the /r/FreeGameFindings thread below.").
BLUESKY_BOILERPLATE_REGEX = re.compile(r"\s*see the .*?thread.*$", re.IGNORECASE)
BLUESKY_FREE_SUFFIX_REGEX = re.compile(r"\s*(?:is|are)\s+(?:now\s+)?free!?\s*$", re.IGNORECASE)

#: The same posts when they are tagged differently, e.g. "[Meta] Subreddit rules update".
BLUESKY_NON_LISTING_TAGS = frozenset(
    {
        "announcement",
        "discussion",
        "meta",
        "mod post",
        "news",
        "psa",
        "question",
        "weekly",
        "weekly thread",
    }
)


def is_aggregate_post(text: str) -> bool:
    """
    True for the FGF weekly thread and its other non-giveaway posts.

    These are discussion posts rather than listings: they carry no platform tag and their
    bodies link to a pile of stores, so resolving one announces an arbitrary game.
    """
    stripped = (text or "").strip()
    tag_match = BLUESKY_PLATFORM_TAG_REGEX.match(stripped)
    tag = tag_match.group(1).strip().lower() if tag_match else ""

    if tag:
        return tag in BLUESKY_NON_LISTING_TAGS or is_aggregate_thread(tag)

    first_line = stripped.splitlines()[0] if stripped else ""
    return is_aggregate_thread(first_line)


def is_listing_tag(platform_tag: str, content_tag: str) -> bool:
    """A listing carries either a known platform tag or a (Game)/(DLC)/(Other) marker."""
    return bool(platforms_from_text(platform_tag) or content_tag.strip())


def strip_query_string(url: str) -> str:
    """Drop query strings and fragments, which carry per-visit tracking on Reddit links."""
    return url.split("?", 1)[0].split("#", 1)[0].rstrip("/")


def split_bluesky_title(text: str) -> tuple[str, str, str]:
    """
    Split a Bluesky listing into ``(platform_tag, content_tag, title)``.

    Posts look like ``[Steam] (Game) Blair Witch is free!``; both leading tags are pulled
    off the title and used for the platform and content type. The trailing link is dropped
    from the title but kept in the full post text.
    """
    remainder = text.strip()
    platform_tag = ""
    content_tag = ""

    for _ in range(2):
        match = BLUESKY_PLATFORM_TAG_REGEX.match(remainder)
        if match:
            platform_tag = platform_tag or match.group(1)
            remainder = remainder[match.end() :]
            continue

        match = BLUESKY_CONTENT_TAG_REGEX.match(remainder)
        if match:
            content_tag = content_tag or match.group(1)
            remainder = remainder[match.end() :]
            continue

        break

    remainder = BLUESKY_URL_REGEX.sub(" ", remainder).strip()
    first_line = remainder.splitlines()[0].strip() if remainder else ""

    title = BLUESKY_BOILERPLATE_REGEX.sub("", first_line).strip()
    title = BLUESKY_FREE_SUFFIX_REGEX.sub("", title).strip()
    return platform_tag, content_tag, title


def bluesky_listing_url(record: dict[str, Any], post: dict[str, Any]) -> str:
    """Pick the listing URL: the post's link facet, a URL in the body, or the post permalink."""
    for facet in record.get("facets") or []:
        for feature in (facet or {}).get("features") or []:
            if (feature or {}).get("$type") != BLUESKY_LINK_FEATURE:
                continue
            uri = str((feature or {}).get("uri") or "").strip()
            if uri:
                return strip_query_string(uri)

    body_match = BLUESKY_URL_REGEX.search(str(record.get("text") or ""))
    if body_match:
        return strip_query_string(body_match.group(0).rstrip(".,;:"))

    uri = str(post.get("uri") or "")
    if uri.startswith("at://"):
        return f"https://bsky.app/profile/{BLUESKY_ACTOR}/post/{uri.rsplit('/', 1)[-1]}"

    return ""


def parse_bluesky_post(item: dict[str, Any]) -> FreeGame | None:
    """Normalize a single post from the author feed, skipping replies and aggregate threads."""
    post = (item or {}).get("post") or {}
    record = post.get("record") or {}

    # Replies are comments on someone else's giveaway, not listings.
    if record.get("reply"):
        return None

    text = str(record.get("text") or "").strip()
    if not text:
        return None

    # The weekly thread and other discussion posts are not giveaways; skip them before any
    # link in their body can be resolved as "the" free game.
    if is_aggregate_post(text):
        logger.debug(f"Skipping FGF aggregate post: {text.splitlines()[0][:80]}")
        return None

    platform_tag, content_tag, title = split_bluesky_title(text)
    if not is_listing_tag(platform_tag, content_tag):
        logger.debug(f"Skipping untagged Bluesky post: {text.splitlines()[0][:80]}")
        return None
    if not title:
        return None

    url = bluesky_listing_url(record, post)
    if not url:
        return None

    return FreeGame(
        source=SOURCE_BLUESKY,
        source_id=str(post.get("uri") or url),
        title=title,
        url=url,
        platforms=platforms_from_text(platform_tag),
        text=text,
        expires_at=None,
        content_type=classify_content(content_tag),
    )


def parse_bluesky_feed(payload: Any) -> list[FreeGame]:
    """Normalize an ``app.bsky.feed.getAuthorFeed`` response."""
    if not isinstance(payload, dict):
        return []

    games: list[FreeGame] = []
    for item in payload.get("feed") or []:
        if not isinstance(item, dict):
            continue
        game = parse_bluesky_post(item)
        if game:
            games.append(game)
    return games


class BlueskyFreeGamesFetcher:
    """The r/FreeGameFindings Bluesky mirror. Links point at Reddit threads, not stores."""

    name = SOURCE_BLUESKY

    def __init__(self, session: aiohttp.ClientSession, interval: float = DEFAULT_FETCH_INTERVAL):
        self.session = session
        self.rate_limiter = RateLimiter(calls_per_second=1.0 / interval)

    async def fetch_games(self) -> list[FreeGame]:
        payload = await fetch_json(
            self.session,
            BLUESKY_FEED_URL,
            params={"actor": BLUESKY_ACTOR, "limit": BLUESKY_FEED_LIMIT},
            limiter=self.rate_limiter,
        )
        return parse_bluesky_feed(payload)


# --- Fan-in -----------------------------------------------------------------


class FreeGamesFetcher(Protocol):
    """The shape every free-game fetcher shares."""

    name: str

    async def fetch_games(self) -> list[FreeGame]: ...


#: Epic first so that dedupe, which keeps the first sighting, prefers the direct store link
#: over Bluesky's Reddit-thread link.
DEFAULT_FETCHERS = (EpicFreeGamesFetcher, GamerPowerFreeGamesFetcher, BlueskyFreeGamesFetcher)


def default_free_games_fetchers(session: aiohttp.ClientSession) -> list[FreeGamesFetcher]:
    """Build the default fan-in for a scan."""
    return [fetcher_class(session) for fetcher_class in DEFAULT_FETCHERS]


async def fetch_all_games(fetchers: Sequence[FreeGamesFetcher]) -> list[FreeGame]:
    """
    Query every fetcher concurrently, skipping (and logging) the ones that fail.

    The fetchers are independent adapters, so a single dead feed degrades the scan instead
    of failing it.
    """
    results = await asyncio.gather(*(fetcher.fetch_games() for fetcher in fetchers), return_exceptions=True)

    games: list[FreeGame] = []
    for fetcher, result in zip(fetchers, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(f"Fetcher '{fetcher.name}' failed; continuing without it: {result}")
            continue
        logger.info(f"Fetcher '{fetcher.name}' returned {len(result)} listing(s)")
        games.extend(result)

    return games
