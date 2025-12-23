# BountyHunter — Free Games Scout

A Discord bot that automatically monitors Bluesky for free game announcements and posts them to your Discord server. Supports multiple game stores including Steam, Epic Games Store, itch.io, and PlayStation Store.

## Features

- 🎮 Multi-platform game tracking (Steam, Epic, itch.io, PlayStation)
- 📱 Automatic Bluesky feed monitoring from @freegamefindings.bsky.social
- 💾 SQLite-backed persistent storage with intelligent caching
- 🔔 Per-server channel subscriptions with optional role mentions
- 🔗 Reddit post expansion for detailed game information
- 🎨 Rich Discord embeds with game details, images, and pricing
- ⚙️ Configurable polling intervals and admin controls

## Requirements

- Python 3.11+
- Discord bot token with required permissions (see below)
- `mise` (optional, for tool management)
- `uv` (optional, for fast dependency management)

## Environment Variables

Create a `.env` file based on `.env.template`:

- **BOT_TOKEN** (required) — Your Discord bot token
- **DATABASE_PATH** (optional) — Path to SQLite database file (default: `./data/bountyhunter.db`)
- **POLL_INTERVAL** (optional) — Minutes between automatic checks (default: `30`)
- **ADMIN_DISCORD_ID** (optional) — Discord user ID for admin commands and error notifications
- **LOG_LEVEL** (optional) — Logging verbosity (default: `INFO`)
