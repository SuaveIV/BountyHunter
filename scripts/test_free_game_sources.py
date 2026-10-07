"""
Manual harness for the free-game fetchers.

    uv run python scripts/test_free_game_sources.py            # live endpoints
    uv run python scripts/test_free_game_sources.py --offline   # parsers + filters only

The offline mode replays small fixtures so the parsing and filtering rules can be checked
without network access; live mode hits Epic, GamerPower and Bluesky for real.
"""

import argparse
import asyncio
import sys

import aiohttp

from bounty_core.fetcher import (
    CONTENT_DLC,
    BlueskyFreeGamesFetcher,
    EpicFreeGamesFetcher,
    FreeGame,
    GamerPowerFreeGamesFetcher,
    dedupe_games,
    filter_games,
    parse_bluesky_feed,
    parse_gamerpower_giveaways,
    rejection_reason,
)

FETCHERS = (EpicFreeGamesFetcher, GamerPowerFreeGamesFetcher, BlueskyFreeGamesFetcher)

OFFLINE_GAMERPOWER = [
    {
        "id": 1,
        "title": "Some Free Game",
        "description": "A description",
        "instructions": "Redeem on Steam",
        "status": "active",
        "type": "game",
        "platforms": "PC, Steam",
        "end_date": "N/A",
        "open_giveaway_url": "https://www.gamerpower.com/open/some-free-game",
    },
    {
        "id": 2,
        "title": "Mobile Only Game",
        "status": "active",
        "type": "game",
        "platforms": "Android",
        "open_giveaway_url": "https://www.gamerpower.com/open/mobile-only",
    },
    {
        "id": 3,
        "title": "Follow Us For A Key",
        "status": "active",
        "type": "game",
        "platforms": "PC, Steam",
        "open_giveaway_url": "https://www.gamerpower.com/open/follow-us",
    },
]

OFFLINE_BLUESKY = {
    "feed": [
        {
            "post": {
                "uri": "at://did:plc:abc/app.bsky.feed.post/1",
                "record": {
                    "text": "[Epic] (Game) Some Free Game is free! See the /r/FreeGameFindings thread below.",
                    "facets": [{"features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://redd.it/abc"}]}],
                },
            }
        },
        {
            "post": {
                "uri": "at://did:plc:abc/app.bsky.feed.post/2",
                "record": {
                    "text": "[Steam] (DLC) Extra Content is free! See the /r/FreeGameFindings thread below.",
                    "facets": [{"features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://redd.it/def"}]}],
                },
            }
        },
    ]
}


def report(games: list[FreeGame]) -> int:
    """Print accepted and rejected listings, then return a shell exit code."""
    accepted = filter_games(games)
    unique = dedupe_games(accepted)

    rejected: dict[str, list[str]] = {}
    for game in games:
        reason = rejection_reason(game)
        if reason:
            rejected.setdefault(reason, []).append(f"{game.source}:{game.title}")

    print(f"\n{len(games)} fetched, {len(accepted)} accepted, {len(unique)} after dedupe\n")
    for game in unique:
        expires = f" (ends {game.expires_at})" if game.expires_at else ""
        print(f"  [{game.source}/{game.content_type}] {game.title}{expires}\n    {game.url}")

    if rejected:
        print("\nRejected:")
        for reason, entries in sorted(rejected.items()):
            print(f"  {reason} ({len(entries)}): {', '.join(entries[:3])}")

    return 0


def run_offline() -> int:
    print("Offline fixtures\n")
    fixtures = parse_gamerpower_giveaways(OFFLINE_GAMERPOWER) + parse_bluesky_feed(OFFLINE_BLUESKY)
    fixtures.append(
        FreeGame(
            source="epic",
            source_id="3",
            title="Some Free Game",
            url="https://store.epicgames.com/en-US/p/some-free-game",
            platforms={"epic"},
            text="Some Free Game\nA description",
            content_type=CONTENT_DLC,
        )
    )
    return report(fixtures)


async def run_live() -> int:
    games: list[FreeGame] = []
    failures = 0

    async with aiohttp.ClientSession() as session:
        for fetcher_class in FETCHERS:
            fetcher = fetcher_class(session)
            try:
                found = await fetcher.fetch_games()
            except Exception as e:
                print(f"FAIL {fetcher.name}: {e}")
                failures += 1
                continue
            print(f"OK   {fetcher.name}: {len(found)} listing(s)")
            games.extend(found)

    report(games)
    return 1 if not games and failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="replay fixtures instead of hitting the feeds")
    args = parser.parse_args()

    if args.offline:
        return run_offline()
    return asyncio.run(run_live())


if __name__ == "__main__":
    sys.exit(main())
