# Contributing to BountyHunter

Thank you for your interest in contributing to BountyHunter! This guide provides an overview of the architecture and development practices.

## Architecture Overview

BountyHunter follows a modular architecture separating the core business logic from the Discord interface.

### Core Modules (`src/bounty_core/`)

The `bounty_core` package contains all logic independent of Discord.

* **`store.py`**: The data access layer. Uses SQLAlchemy (Async) to manage SQLite interactions.
  * **`db/`**: Contains database models (`models.py`) and connection logic (`engine.py`).
* **Managers (`*_api_manager.py`)**: Specialized classes for fetching data from specific stores (Steam, Epic, Itch, etc.). They handle HTTP requests, parsing, and error handling.
* **`fetcher.py`**: Handles RSS feed fetching (e.g., Reddit) to find new deals.
* **`parser.py`**: Regex and HTML parsing utilities to extract game titles and IDs.
* **`rate_limiter.py`**: A token-bucket implementation to respect API rate limits.

### Discord Modules (`src/bounty_discord/`)

The `bounty_discord` package contains the Discord bot logic.

* **`gunship.py`**: The main Bot class. Initializes resources (DB, Managers).
* **`cogs/`**: Discord.py extensions (Cogs).
  * `visor.py` (SectorVisor): The main loop that scans feeds and announces games.
  * `codex.py`: Commands for price checking.
  * `beacons.py`: Commands for managing subscriptions.
  * `admin.py`: Admin-only debugging tools.

## Development Setup

We use `uv` for dependency management.

1. **Install uv**: Follow instructions at [astral.sh/uv](https://astral.sh/uv).
2. **Sync environment**: `uv sync`
3. **Run tests**: `just test` (or `uv run pytest`)
4. **Lint/Format**: `just check` / `just fix`

## Coding Standards

* **Type Safety**: All code must be fully type-hinted. We use `pyright` for enforcement.
* **Formatting**: We use `ruff` for both linting and formatting.
* **Error Handling**: Use the exceptions defined in `bounty_core.exceptions`. Do not swallow errors silently unless explicitly intended (e.g., caching logic).
* **Async**: The entire codebase is async. Avoid blocking calls (like `requests` or `time.sleep`).

## Adding a New Store

To add support for a new store (e.g., GOG):

1. Create `src/bounty_core/gog_api_manager.py` implementing fetch logic.
2. Add a generic wrapper in `src/bounty_core/gog.py` (optional, but follows pattern).
3. Update `src/bounty_discord/utils.py:resolve_game_details` to handle the new store logic.
4. Initialize the manager in `src/bounty_discord/gunship.py`.
