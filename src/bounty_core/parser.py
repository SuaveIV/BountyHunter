import re
from typing import Final

from bs4 import BeautifulSoup

from .constants import DENY_DOMAINS

STEAM_APP_REGEX = re.compile(r"store\.steampowered\.com/app/(\d+)")
ITCH_GAME_REGEX = re.compile(r"(https?://[a-zA-Z0-9-]+\.itch\.io/[a-zA-Z0-9-]+)")
PS_GAME_REGEX = re.compile(r"(https?://store\.playstation\.com/(?:[^/]+/)?product/([a-zA-Z0-9_-]+))")
EPIC_GAME_REGEX = re.compile(r"store\.epicgames\.com/(?:[^/]+/)?p/([^/\s?]+)")
GOG_GAME_REGEX = re.compile(r"(https?://(?:www\.)?gog\.com/(?:[a-z]{2}/)?game/[a-zA-Z0-9_-]+)")
URL_REGEX = re.compile(r"(https?://[^\s]+)")
FGF_TITLE_REGEX = re.compile(r"^[\[\(].*?[\]\)]\s*(?:\(.*?\)\s*)?(.+?) is free", re.IGNORECASE | re.MULTILINE)
FGF_PSA_REGEX = re.compile(r"^\[PSA\]\s*(.+?)\s*(?:are|is) complimentary", re.IGNORECASE | re.MULTILINE)
FGF_TYPE_REGEX = re.compile(r"\[.*?\]\s*\((.*?)\)", re.IGNORECASE)
PSA_CHECK_REGEX = re.compile(r"^\[PSA\]", re.IGNORECASE)

# --- Title normalization ----------------------------------------------------

#: Noise words stripped before comparing titles: the filler words and storefront names that
#: show up in "X (Epic Games) Giveaway" style listings.
TITLE_NOISE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "amazon",
        "epic",
        "epicgames",
        "free",
        "freebie",
        "game",
        "games",
        "giveaway",
        "gog",
        "itch",
        "key",
        "prime",
        "steam",
    }
)

TITLE_PARENS_REGEX = re.compile(r"[\(\[\{][^)\]\}]*[\)\]\}]")
TITLE_NON_ALNUM_REGEX = re.compile(r"[^a-z0-9]+")


def normalize_title(title: str) -> str:
    """
    Reduce a listing title to a comparison key.

    Parentheticals are dropped ("BURIED STARS (Epic Games) Giveaway" -> "buried stars"),
    followed by punctuation and a small set of noise words. The heuristic merges
    generously, which is what we want for duplicates, but it will occasionally merge two
    differently titled listings for the same game.
    """
    if not title:
        return ""

    cleaned = TITLE_PARENS_REGEX.sub(" ", title.lower())
    cleaned = TITLE_NON_ALNUM_REGEX.sub(" ", cleaned)
    words = [word for word in cleaned.split() if word not in TITLE_NOISE_WORDS]
    return " ".join(words)


def titles_match(query: str, candidate: str) -> bool:
    """
    Loose title equality, for validating fuzzy search results.

    Store and price APIs answer a bad query with their best guess rather than nothing (ITAD
    happily returns a keyword-stuffed listing for a garbled title), so a returned title has
    to account for every word we searched for. A candidate that only covers part of the
    query is a different edition, or the base game sitting behind a DLC giveaway, which is
    how a "Scarlet Crest Armor" giveaway once went out named after the Switch 2 edition.
    """
    wanted = normalize_title(query)
    found = normalize_title(candidate)

    if not wanted or not found:
        return False

    if wanted == found:
        return True

    # A candidate may be more specific than the query ("Bounty Train" against "Bounty
    # Train: The Board Game"), never less.
    return set(wanted.split()) <= set(found.split())


def determine_content_type(text: str) -> str:
    """
    Determines the type of content based on the title.
    Returns: 'GAME', 'ITEM', 'INFO', or 'UNKNOWN'
    """
    if PSA_CHECK_REGEX.search(text):
        return "INFO"

    match = FGF_TYPE_REGEX.search(text)
    if match:
        tag = match.group(1).lower()
        if tag == "game":
            return "GAME"
        return "ITEM"

    return "UNKNOWN"


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


def extract_gog_urls(text: str) -> set[str]:
    """Extracts unique GOG game URLs from a block of text."""
    return set(GOG_GAME_REGEX.findall(text))


def is_safe_link(url: str) -> bool:
    """Filters out known spam/raffle domains."""
    return not any(domain in url for domain in DENY_DOMAINS)


def extract_og_data(soup: BeautifulSoup) -> dict[str, str | None]:
    """
    Extracts Open Graph title and image from a BeautifulSoup object.
    Handles potential list content in meta tags.
    """
    data: dict[str, str | None] = {"title": None, "image": None}

    # Extract Title
    og_title = soup.find("meta", property="og:title")
    if og_title:
        content = og_title.get("content")
        if isinstance(content, str):
            data["title"] = content
        elif isinstance(content, list) and content and isinstance(content[0], str):
            data["title"] = content[0]

    # Extract Image
    og_image = soup.find("meta", property="og:image")
    if og_image:
        content = og_image.get("content")
        if isinstance(content, str):
            data["image"] = content
        elif isinstance(content, list) and content and isinstance(content[0], str):
            data["image"] = content[0]

    return data
