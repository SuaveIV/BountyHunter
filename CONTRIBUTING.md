# Contributing to BountyHunter

## Architecture

The app has two parts: the core logic and the Discord interface.

### Core (`src/bounty_core/`)

This package handles the logic. It doesn't know Discord exists.

- **`store.py`**: Data access. Uses SQLAlchemy (Async) with SQLite.
  - **`db/`**: Models (`models.py`) and connection logic (`engine.py`).
- **Managers (`*_api_manager.py`)**: They fetch data from stores (Steam, Epic, Itch, etc.), handling the HTTP requests and parsing.
- **`fetcher.py`**: Checks RSS feeds (like Reddit) for deals.
- **`parser.py`**: Regex and HTML parsing tools to find game titles and IDs.
- **`rate_limiter.py`**: Token-bucket implementation to respect API limits.

### Discord (`src/bounty_discord/`)

This package runs the bot.

- **`gunship.py`**: Main Bot class. Starts the DB and Managers.
- **`cogs/`**: Discord.py extensions.
  - `visor.py`: Scanning loop that finds and announces games.
  - `codex.py`: Price check commands.
  - `beacons.py`: Subscription management.
  - `admin.py`: Debugging tools.

## Setup

We use `uv`.

1. **Install uv**: [astral.sh/uv](https://astral.sh/uv).
2. **Sync**: `uv sync`
3. **Test**: `just test` (or `uv run pytest`)
4. **Lint**: `just check` / `just fix`

## Standards

- **Types**: Everything is typed. `pyright` enforces it.
- **Format**: `ruff` handles linting and formatting.
- **Errors**: Use `bounty_core.exceptions`. Don't swallow errors unless you mean to.
- **Async**: No blocking calls (like `requests` or `time.sleep`).

## Adding a Store

To add a store (e.g., GOG):

1. Create `src/bounty_core/gog_api_manager.py` with the fetch logic.
2. Add a wrapper in `src/bounty_core/gog.py` (optional, but consistent).
3. Update `src/bounty_discord/utils.py:resolve_game_details` to handle the new store.
4. Initialize the manager in `src/bounty_discord/gunship.py`.
