import re
from typing import Any

# Heuristics ported from FamilyBot
DENY_DOMAINS = {"givee.club", "gleam.io", "indiegala.com", "rafflecopter.com", "woobox.com"}
STEAM_APP_REGEX = re.compile(r"store\.steampowered\.com/app/(\d+)")
ITCH_GAME_REGEX = re.compile(r"(https?://[a-zA-Z0-9-]+\.itch\.io/[a-zA-Z0-9-]+)")
PS_GAME_REGEX = re.compile(r"(https?://store\.playstation\.com/(?:[^/]+/)?product/([a-zA-Z0-9_-]+))")
EPIC_GAME_REGEX = re.compile(r"store\.epicgames\.com/(?:[^/]+/)?p/([^/\s?]+)")
URL_REGEX = re.compile(r"(https?://[^\s]+)")
REDDIT_REGEX = re.compile(
    r"https?://(?:www\.|old\.|new\.)?reddit\.com/r/[^/]+/comments/[^/]+|https?://redd\.it/[a-zA-Z0-9]+",
    re.IGNORECASE,
)
FGF_TITLE_REGEX = re.compile(r"^[\[\(].*?[\]\)]\s*(?:\(.*?\)\s*)?(.+?) is free", re.IGNORECASE)
FGF_PSA_REGEX = re.compile(r"^\[PSA\]\s*(.+?)\s*(?:are|is) complimentary", re.IGNORECASE)


def extract_game_title(text: str) -> str | None:
    """Attempts to extract the game title from the post text."""
    # Try generic 'is free' pattern
    match = FGF_TITLE_REGEX.search(text)
    if match:
        return match.group(1).strip()

    # Try PSA pattern
    match = FGF_PSA_REGEX.search(text)
    if match:
        return match.group(1).strip()

    return None


def extract_steam_ids(text: str) -> set[str]:
    """Extracts unique Steam App IDs from a block of text."""
    return set(STEAM_APP_REGEX.findall(text))


def extract_epic_slugs(text: str) -> set[str]:
    """Extracts unique Epic Games Store slugs from a block of text."""
    return set(EPIC_GAME_REGEX.findall(text))


def extract_itch_urls(text: str) -> set[str]:
    """Extracts unique itch.io game URLs from a block of text."""
    return set(ITCH_GAME_REGEX.findall(text))


def extract_ps_urls(text: str) -> set[str]:
    """Extracts unique PlayStation Store game URLs from a block of text."""
    # PS_GAME_REGEX matches the full URL in group 1
    matches = PS_GAME_REGEX.findall(text)
    return {m[0] for m in matches}


def extract_links(post_data: dict[str, Any]) -> set[str]:
    """
    Extracts links from a Bluesky post object using facets, embeds, and raw text.
    """
    links = set()

    # 1. Extract from facets (Bluesky rich text metadata)
    record = post_data.get("record", {})
    if "facets" in record:
        for facet in record["facets"]:
            for feature in facet.get("features", []):
                if feature.get("$type") == "app.bsky.richtext.facet#link":
                    links.add(feature["uri"])

    # 2. Extract from text content via Regex (fallback)
    text = record.get("text", "")
    links.update(URL_REGEX.findall(text))

    # 3. Extract from external embeds
    embed = post_data.get("embed", {})
    if embed.get("$type") == "app.bsky.embed.external#view":
        external = embed.get("external", {})
        if "uri" in external:
            links.add(external["uri"])

    return links


def is_safe_link(url: str) -> bool:
    """Filters out known spam/raffle domains."""
    return not any(domain in url for domain in DENY_DOMAINS)


def is_reddit_link(url: str) -> bool:
    """Checks if a URL is a Reddit post."""
    return bool(REDDIT_REGEX.search(url))


def extract_links_from_reddit_json(data: Any) -> set[str]:
    """Extracts links from a Reddit post JSON response."""
    links = set()
    # Reddit JSON is a list of listings. [0] is the post, [1] is comments.
    if isinstance(data, list) and len(data) > 0:
        children = data[0].get("data", {}).get("children", [])
        if children:
            post_data = children[0].get("data", {})

            if "url" in post_data:
                links.add(post_data["url"])

            if "selftext" in post_data:
                links.update(URL_REGEX.findall(post_data["selftext"]))
    return links
