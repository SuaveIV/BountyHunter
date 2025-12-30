import re

# Heuristics ported from FamilyBot
DENY_DOMAINS = {"givee.club", "gleam.io", "indiegala.com", "rafflecopter.com", "woobox.com"}
STEAM_APP_REGEX = re.compile(r"store\.steampowered\.com/app/(\d+)")
ITCH_GAME_REGEX = re.compile(r"(https?://[a-zA-Z0-9-]+\.itch\.io/[a-zA-Z0-9-]+)")
PS_GAME_REGEX = re.compile(r"(https?://store\.playstation\.com/(?:[^/]+/)?product/([a-zA-Z0-9_-]+))")
EPIC_GAME_REGEX = re.compile(r"store\.epicgames\.com/(?:[^/]+/)?p/([^/\s?]+)")
URL_REGEX = re.compile(r"(https?://[^\s]+)")
FGF_TITLE_REGEX = re.compile(r"^[\[\(].*?[\]\)]\s*(?:\(.*?\)\s*)?(.+?) is free", re.IGNORECASE | re.MULTILINE)
FGF_PSA_REGEX = re.compile(r"^\[PSA\]\s*(.+?)\s*(?:are|is) complimentary", re.IGNORECASE | re.MULTILINE)


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


def is_safe_link(url: str) -> bool:
    """Filters out known spam/raffle domains."""
    return not any(domain in url for domain in DENY_DOMAINS)
