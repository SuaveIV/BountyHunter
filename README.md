# BountyHunter

BountyHunter monitors [r/FreeGameFindings](https://www.reddit.com/r/FreeGameFindings/) and posts new free game offers to your Discord server. It grabs details from Steam, Epic, itch.io, GOG, and Amazon Prime Gaming to build a clean embed with the original price and release info.

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
