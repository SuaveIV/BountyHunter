# BountyHunter

BountyHunter watches several free-game feeds and posts new free game offers to your Discord server. It grabs details from Steam, Epic, itch.io, GOG, and Amazon Prime Gaming to build a clean embed with the original price and release info.

## Sources

The scanner fans several independent, keyless feeds in, keeps going when one of them fails, and deduplicates across all of them:

| Source           | Feed                                        | Notes                                                                                                                   |
| ---------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Epic Games Store | `freeGamesPromotions`                       | Direct store links.                                                                                                     |
| GamerPower       | `/api/giveaways?type=game` and `?type=loot` | Queried once per type; the API rejects multi-type queries and 404s on `dlc`/`beta`. Attribution required, max 10 req/s. |
| Bluesky          | `freegamefindings.bsky.social`              | Mirror of r/FreeGameFindings. Links point at Reddit threads, not stores.                                                |

Reddit's own RSS feed is no longer polled: Reddit is retiring RSS (Nov 2026) and public API access (Mar 2027), and the feed already returns 403s. Its fetcher is kept in `bounty_core/fetcher.py` rather than deleted, so it can be adapted back into the fan-in if the feed recovers before Reddit retires it for good.

Listings are normalized into one `FreeGame` model, filtered (aggregate threads, excluded keywords, task giveaways, blocked domains, platform whitelist, Steam link trust), and deduplicated by source id and by normalized title, so the same game found by two sources is announced once. The first run against an empty database seeds the existing listings instead of dumping the whole backlog into the channel.

FGF's weekly thread and its themed "mega threads" are not listings — they are single posts that link to a pile of stores, so resolving one would announce whichever game happened to be linked first. They are detected and skipped explicitly. Fuzzy title lookups (ITAD) are validated against the listing title too, so a lookup that fails stays a failure instead of announcing an unrelated game.

## Features

- **Store Support:** Fetches metadata from Steam, Epic, itch.io, PlayStation, GOG, and Amazon.
- **Price Checks:** Uses the `!price` command to check IsThereAnyDeal for current lows.
- **Reliability:** Built with `discord.py` and `SQLAlchemy`. Uses SQLite (WAL mode) for storage.
- **Notifications:** Configurable per channel. You can tag a specific role when a game drops.

## Commands

### **Public**

- `!subscribe [role]` — Post free games to this channel. Optionally mentions a role. (Requires "Manage Guild").
- `!unsubscribe` — Stop posting in this channel.
- `!price <game>` — Check prices and history on IsThereAnyDeal.

**Admin**
(Requires `ADMIN_DISCORD_ID` in `.env`)

- `!status` — Check uptime and last scan time.
- `!force_free` — Run the scraper immediately.
- `!test_embed <id/url>` — Debug commands to generate embeds for specific stores.

## Setup

We use `uv` and `mise` to manage dependencies.

1. **Configure**
   Copy `.env.example` to `.env` and add your `BOT_TOKEN`.

   ```bash
   cp .env.example .env
   ```

   **Polling Interval**

   - Set `POLL_INTERVAL` in minutes (minimum: 1 minute).
   - The bot will check the feed every `POLL_INTERVAL` minutes.

1. **Install**

   ```bash
   just setup
   ```

1. **Run**

   ```bash
   just run
   ```

## Docker

```bash
docker-compose up -d --build
```

## Development

Run `just check` to run the full suite of linters (Ruff), type checkers (Pyright), and tests (pytest).

Built with `discord.py`, `aiohttp`, `feedparser`, and `BeautifulSoup4`.
