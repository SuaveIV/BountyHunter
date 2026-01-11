import time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from bounty_core.db.engine import Database
from bounty_core.db.models import GameCache, SeenPost, Subscription


class Store:
    """
    Data access layer for BountyHunter.

    Uses SQLAlchemy (Async) with an underlying SQLite database (in WAL mode).
    Manages caching of game details, seen posts tracking, and user subscriptions.
    """

    def __init__(self, db: Database):
        self.db = db

    async def setup(self):
        """
        Initializes the database connection.
        Legacy compatibility: The old store had a setup() method.
        """
        await self.db.connect()

    async def close(self):
        await self.db.close()

    # --- Seen Posts ---

    async def is_post_seen(self, post_id: str) -> bool:
        async with self.db.session as session:
            stmt = select(SeenPost).where(SeenPost.id == post_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def mark_post_seen(self, post_id: str):
        async with self.db.session as session:
            # Using INSERT OR IGNORE via dialect specific
            stmt = sqlite_insert(SeenPost).values(id=post_id, timestamp=time.time())
            stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
            await session.execute(stmt)
            await session.commit()

    # --- Subscriptions ---

    async def get_subscriptions(self) -> list[tuple[int, int, int | None]]:
        async with self.db.session as session:
            stmt = select(Subscription)
            result = await session.execute(stmt)
            subs = result.scalars().all()
            return [(s.guild_id, s.channel_id, s.role_id) for s in subs]

    async def add_subscription(self, guild_id: int, channel_id: int, role_id: int | None):
        async with self.db.session as session:
            # Upsert
            stmt = sqlite_insert(Subscription).values(guild_id=guild_id, channel_id=channel_id, role_id=role_id)
            stmt = stmt.on_conflict_do_update(
                index_elements=["guild_id", "channel_id"],
                set_={"role_id": role_id},
            )
            await session.execute(stmt)
            await session.commit()

    async def remove_subscription(self, guild_id: int, channel_id: int):
        async with self.db.session as session:
            stmt = delete(Subscription).where(Subscription.guild_id == guild_id, Subscription.channel_id == channel_id)
            await session.execute(stmt)
            await session.commit()

    # --- Generic Game Cache (Replacing 4 separate methods) ---

    async def get_cached_details(self, store: str, identifier: str) -> dict[str, Any] | None:
        async with self.db.session as session:
            stmt = select(GameCache).where(GameCache.store == store, GameCache.identifier == identifier)
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()
            return entry.data if entry else None

    async def cache_details(self, store: str, identifier: str, data: dict[str, Any], permanent: bool = False):
        async with self.db.session as session:
            stmt = sqlite_insert(GameCache).values(
                store=store,
                identifier=identifier,
                fetched_at=time.time(),
                data=data,
                permanent=permanent,
            )
            # Update on conflict
            stmt = stmt.on_conflict_do_update(
                index_elements=["store", "identifier"],
                set_={"fetched_at": time.time(), "data": data, "permanent": permanent},
            )
            await session.execute(stmt)
            await session.commit()

    # --- Compatibility Wrappers (Optional, for easy migration) ---

    async def get_cached_game_details(self, appid: str) -> dict[str, Any] | None:
        return await self.get_cached_details("steam", appid)

    async def cache_game_details(self, appid: str, data: dict, permanent: bool = False):
        await self.cache_details("steam", appid, data, permanent)

    async def get_cached_epic_details(self, slug: str) -> dict[str, Any] | None:
        return await self.get_cached_details("epic", slug)

    async def cache_epic_details(self, slug: str, data: dict, permanent: bool = False):
        await self.cache_details("epic", slug, data, permanent)

    async def get_cached_itch_details(self, url: str) -> dict[str, Any] | None:
        return await self.get_cached_details("itch", url)

    async def cache_itch_details(self, url: str, data: dict, permanent: bool = False):
        await self.cache_details("itch", url, data, permanent)

    async def get_cached_ps_details(self, url: str) -> dict[str, Any] | None:
        return await self.get_cached_details("ps", url)

    async def cache_ps_details(self, url: str, data: dict, permanent: bool = False):
        await self.cache_details("ps", url, data, permanent)

    async def get_cached_gog_details(self, url: str) -> dict[str, Any] | None:
        return await self.get_cached_details("gog", url)

    async def cache_gog_details(self, url: str, data: dict, permanent: bool = False):
        await self.cache_details("gog", url, data, permanent)

    async def clear_cache(self):
        async with self.db.session as session:
            await session.execute(delete(GameCache))
            await session.commit()
