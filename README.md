# BountyHunter — Free Games Scout

A Discord bot that automatically monitors Reddit for free game announcements and posts them to your Discord server. Supports multiple game stores including Steam, Epic Games Store, itch.io, PlayStation Store, GOG, and Amazon Prime Gaming.

## Features

- 🎮 **Multi-platform game tracking**: Steam, Epic Games Store, itch.io, PlayStation Store, GOG, and Amazon Prime Gaming.
- 📱 **Automatic Reddit monitoring**: Tracks [r/FreeGameFindings](https://www.reddit.com/r/FreeGameFindings/) via RSS for the latest deals.
- 💰 **Price Checking**: Check game prices and historical lows using IsThereAnyDeal (`!price`).
- 💾 **Pooled Storage**: SQLAlchemy-backed storage with connection pooling and WAL mode for high reliability.
- 🔔 **Smart Notifications**: Per-server channel subscriptions with optional role pings.
- 🔗 **Rich Content**: Expands external links and generates detailed embeds with game info, images, and pricing.
- ⚙️ **Robust Architecture**: Built-in rate limiting, standardized error handling, and 100% type safety.

## Commands

### Public Commands

- `!subscribe [role]` — Subscribe the current channel to free game announcements. Optionally tag a role.
  - *Requires "Manage Guild" permission.*
- `!unsubscribe` — Unsubscribe the current channel.
  - *Requires "Manage Guild" permission.*
- `!price <game title>` — Check the current best price and historical low for a game via IsThereAnyDeal.

### Admin Commands (DM Only)

*Requires `ADMIN_DISCORD_ID` to be set in `.env`.*

- `!status` — Show bot uptime and last check time.
- `!force_free` — Force a check for free games immediately.
- `!test_embed_all` — Generate example embeds for all supported stores.
- `!test_embed <steam_id>` — Generate a test embed for a Steam game.
- `!test_embed_epic <slug>` — Generate a test embed for an Epic Games store slug.
- `!test_embed_itch <url>` — Generate a test embed for an itch.io URL.
- `!test_embed_ps <url>` — Generate a test embed for a PlayStation Store URL.
- `!test_embed_url <url> [text]` — Generate a test embed for any generic URL (GOG, Amazon, Stove, etc.).
- `!test_scraper` — Test the Reddit RSS feed fetcher.

## Requirements

- Python 3.11+
- Discord Bot Token
- [IsThereAnyDeal API Key](https://isthereanydeal.com/about/api/) (optional, for `!price` command)
- `mise` (recommended for tool management) or `uv`

## Setup & Running

This project uses [`mise`](https://mise.jdx.dev/) and [`uv`](https://github.com/astral-sh/uv) for easy environment management.

### 1. Environment Variables

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

- **BOT_TOKEN** (required) — Your Discord bot token.
- **DATABASE_PATH** (optional) — Path to SQLite database (default: `./data/bountyhunter.db`).
- **POLL_INTERVAL** (optional) — Minutes between checks (default: `30`).
- **ADMIN_DISCORD_ID** (optional) — Your Discord User ID for admin commands.
- **LOG_LEVEL** (optional) — Logging verbosity (default: `INFO`).
- **ITAD_API_KEY** (optional) — API Key for IsThereAnyDeal integration.

### 2. Installation (using `just`)

If you have `just` and `mise` installed:

```bash
just setup
```

This will create a virtual environment, install dependencies, and verify everything is working.

### 3. Run the Bot

```bash
just run
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for architectural details and coding standards.

- **Run Tests**: `just test`
- **Full Check**: `just check` (runs lint, format-check, type-check, and tests)

## Docker

You can also run BountyHunter using Docker:

```bash
docker-compose up -d --build
```

## Tech Stack & Credits

BountyHunter is powered by these awesome open-source projects and data sources:

**Core Libraries:**

- [discord.py](https://github.com/Rapptz/discord.py) — API wrapper for Discord.
- [SQLAlchemy](https://www.sqlalchemy.org/) — Database ORM (Async).
- [aiohttp](https://docs.aiohttp.org/) — Async HTTP client.
- [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/) — HTML parsing and scraping.
- [feedparser](https://github.com/kurtmckee/feedparser) — RSS feed parsing.

**Data Sources:**

- **Reddit**: [r/FreeGameFindings](https://www.reddit.com/r/FreeGameFindings/) for discovering new free game announcements.
- **IsThereAnyDeal**: [API](https://isthereanydeal.com/) for price history and metadata enhancement.
