# BountyHunter — Free Games Scout (interactions)

Minimal standalone bot scaffold based on the FamilyBot `free_games` plugin (Discord adapter).
It uses the `interactions` library and a SQLite-backed store for per-server subscriptions.

Requirements
- Python 3.10+
- Discord bot token with guild message permissions

Environment variables
- BOT_TOKEN (required) — your Discord bot token
- DATABASE_PATH (optional) — path to sqlite file, default `./data/bountyhunter.db`
- POLL_INTERVAL (optional) — minutes between automatic checks (default `30`)
- ADMIN_DISCORD_ID (optional) — discord user id allowed to run `!force_free` and receive admin DM on errors
- LOG_LEVEL (optional) — default `INFO`

Quick start (local)
1. pip install -r requirements.txt
2. export BOT_TOKEN="..."
3. python -m bounty_discord.run

Docker
- Build: docker build -t bountyhunter .
- Run (example): docker run -e BOT_TOKEN="..." -v $(pwd)/data:/app/data bountyhunter

What to implement next
- Port the exact Bluesky parsing logic from FamilyBot `free_games.py`.
- Implement SteamAPIManager and fetch_game_details parity (caching and dedupe).
- Add tests (adapt `scripts/test_free_games.py`).
- Add more per-server options (custom poll intervals, enable/disable, last-announced message).