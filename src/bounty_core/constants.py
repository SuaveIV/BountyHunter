from enum import Enum


class Platform(Enum):
    STEAM = "Steam"
    EPIC = "Epic Games Store"
    ITCH = "Itch.io"
    GOG = "GOG.com"
    PLAYSTATION = "PlayStation Store"
    AMAZON = "Amazon Prime Gaming"
    STOVE = "STOVE"


# Heuristics ported from FamilyBot
DENY_DOMAINS = frozenset(
    {
        "givee.club",
        "gleam.io",
        "indiegala.com",
        "keymailer",
        "rafflecopter.com",
        "woobox.com",
        "woovit",
        "stove.com",
        "onstove.com",
    }
)
