# Architecture & Refactoring Plan

This document outlines the roadmap for improving the BountyHunter codebase, focusing on stability, maintainability, and performance.

## Refactoring Plan

### Phase 1: Foundation & Stability (High Priority)

* **Centralize Constants**: Move magic strings and configuration lists (like `DENY_DOMAINS`) to a dedicated `constants.py` to avoid duplication and typos.
* **Harden Configuration**: Implement validation for environment variables to ensure the bot fails fast if misconfigured (e.g., missing Token), rather than failing silently at runtime.
* **Resolve Circular Dependencies**: Refactor `bounty_core` and `bounty_discord` imports. Likely requires creating a separate `models.py` or `types.py` for shared data structures used by both Managers and the core logic.

### Phase 2: Code Quality & Architecture (Medium Priority)

* **Separation of Concerns**: Split `utils.py` in the discord module. Move game data fetching logic to `bounty_core` and keep only Discord UI helpers in `bounty_discord`.
* [x] Standardize Error Handling: Decide on a pattern (Result pattern or Custom Exceptions) and apply it across all API managers.
* **Type Safety**: Audit `cogs/` and `bounty_core` to ensure 100% type hint coverage.

### Phase 3: Performance & Reliability (Medium Priority)

* [x] Database Pooling: Implement a connection pool (e.g., using `aiosqlite` or `sqlalchemy` with pooling) to handle concurrent database requests efficiently. (Migrated to SQLAlchemy Async).
* [x] Rate Limiting & Caching: Abstract the rate limiting logic from `SteamAPIManager` into a decorator or base class and apply it to Epic and Itch managers. (Implemented `RateLimiter` class).

### Phase 4: Testing & Documentation (Low Priority)

* [x] Test Coverage: Write unit tests for `parser.py` covering edge cases (unicode, mixed text). Create integration tests for the database layer. (Completed).
* **Documentation**: Add docstrings to all public functions. Create a `CONTRIBUTING.md` with architectural overview.

---

## TODO List

### Immediate Actions (Quick Wins)

* [x] Create `src/bounty_core/constants.py` for Platforms and Deny Domains.

* [x] Refactor `src/bounty_core/parser.py` to use shared constants.
* [x] Add Pydantic validation to `src/bounty_discord/config.py`.

### Core Refactoring

* [x] Audit `bounty_core` and `bounty_discord` imports to identify and fix circular dependencies.
* [x] Move `get_fallback_details` and `enhance_details_with_itad` from `discord/utils.py` to `bounty_core`.
* [x] Create `ImageUtils` class/module to deduplicate image URL extraction logic (Implemented as `extract_og_data` in `parser.py`).

### Reliability

* [ ] Add `RateLimiter` class to `bounty_core/network.py`.

* [ ] Implement retry logic (backoff) for HTTP requests in all API managers.
* [ ] Update `SectorVisor` to use configurable scheduling intervals.

### Maintenance

* [ ] Rename `.env.template` to `.env.example`.

* [ ] Add regex masking for API keys in `SensitiveDataFilter`.
* [ ] Write docstrings for `SectorVisor` cog.
