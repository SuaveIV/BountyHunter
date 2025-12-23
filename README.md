# BountyHunter — Free Games Scout

Minimal standalone bot based on the '@SuaveIV/FamilyBot' `free_games` plugin (Discord adapter).
It uses `discord.py` and a SQLite-backed store for per-server subscriptions.

Requirements

- Python 3.10+
- Discord bot token with guild message permissions
- `mise` (optional, for tool management)
- `uv` (optional, for fast dependency management)

Environment variables

- BOT_TOKEN (required) — your Discord bot token
- DATABASE_PATH (optional) — path to sqlite file, default `./data/bountyhunter.db`
- POLL_INTERVAL (optional) — minutes between automatic checks (default `30`)
- ADMIN_DISCORD_ID (optional) — discord user id allowed to run `!force_free` and receive admin DM on errors
- LOG_LEVEL (optional) — default `INFO`

Discord Configuration

1. Create a new Application in the Discord Developer Portal.
2. Go to the **Bot** tab:
   - Click **Add Bot**.
   - Uncheck **Public Bot** (optional, keeps it private to you).
   - Enable **Message Content Intent** (required for commands).
   - Copy the **Token** (this is your `BOT_TOKEN`).
3. To invite the bot:
   - Go to **OAuth2** > **URL Generator**.
   - Select `bot` scope.
   - Select permissions: `Read Messages/View Channels`, `Send Messages`, `Embed Links`, `Read Message History`.
   - Copy the generated URL and open it in your browser.
   - *Note: You cannot set a "Default Authorization Link" for private bots; use the URL Generator instead.*

Quick start (local)

1. `just setup` (or `pip install -r requirements.txt`)
2. `export BOT_TOKEN="..."`
3. `just run` (or `python src/bounty_discord/run.py`)

Docker

- Build: docker build -t bountyhunter .
- Run (example): docker run -e BOT_TOKEN="..." -v $(pwd)/data:/app/data bountyhunter

What to implement next

- Port the exact Bluesky parsing logic from FamilyBot `free_games.py`.
- Implement SteamAPIManager and fetch_game_details parity (caching and dedupe).
- Add tests (adapt `scripts/test_free_games.py`).
- Add more per-server options (custom poll intervals, enable/disable, last-announced message).
