import json
import os
import time
from typing import cast

import aiosqlite


class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def setup(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Track seen posts to prevent duplicate announcements
            await db.execute("""
                CREATE TABLE IF NOT EXISTS seen_posts (
                    id TEXT PRIMARY KEY,
                    timestamp REAL
                )
            """)
            # Discord subscriptions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, channel_id)
                )
            """)
            # Steam App Details Cache (T-002)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS steam_app_cache (
                    appid TEXT PRIMARY KEY,
                    fetched_at REAL,
                    data TEXT,
                    permanent INTEGER DEFAULT 0
                )
            """)
            # Epic App Details Cache
            await db.execute("""
                CREATE TABLE IF NOT EXISTS epic_app_cache (
                    slug TEXT PRIMARY KEY,
                    fetched_at REAL,
                    data TEXT,
                    permanent INTEGER DEFAULT 0
                )
            """)
            # Itch.io Game Cache
            await db.execute("""
                CREATE TABLE IF NOT EXISTS itch_game_cache (
                    url TEXT PRIMARY KEY,
                    fetched_at REAL,
                    data TEXT,
                    permanent INTEGER DEFAULT 0
                )
            """)
            # PlayStation Game Cache
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ps_game_cache (
                    url TEXT PRIMARY KEY,
                    fetched_at REAL,
                    data TEXT,
                    permanent INTEGER DEFAULT 0
                )
            """)
            await db.commit()

    async def is_post_seen(self, post_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM seen_posts WHERE id = ?", (post_id,)) as cursor:
                return await cursor.fetchone() is not None

    async def mark_post_seen(self, post_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO seen_posts (id, timestamp) VALUES (?, ?)",
                (post_id, time.time()),
            )
            await db.commit()

    async def get_subscriptions(self) -> list[tuple[int, int, int | None]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT guild_id, channel_id, role_id FROM subscriptions") as cursor:
                return cast(list[tuple[int, int, int | None]], await cursor.fetchall())

    async def get_subscriptions_by_guild(self, guild_id: int) -> list[tuple[int, int, int | None]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT guild_id, channel_id, role_id FROM subscriptions WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                return cast(list[tuple[int, int, int | None]], await cursor.fetchall())

    async def add_subscription(self, guild_id: int, channel_id: int, role_id: int | None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO subscriptions (guild_id, channel_id, role_id) VALUES (?, ?, ?)",
                (guild_id, channel_id, role_id),
            )
            await db.commit()

    async def remove_subscription(self, guild_id: int, channel_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM subscriptions WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
            await db.commit()

    async def get_cached_game_details(self, appid: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM steam_app_cache WHERE appid = ?", (appid,)) as cursor:
                row = await cursor.fetchone()
                return json.loads(row[0]) if row else None

    async def cache_game_details(self, appid: str, data: dict, permanent: bool = False):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO steam_app_cache (appid, fetched_at, data, permanent) VALUES (?, ?, ?, ?)",
                (appid, time.time(), json.dumps(data), 1 if permanent else 0),
            )
            await db.commit()

    async def get_cached_epic_details(self, slug: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM epic_app_cache WHERE slug = ?", (slug,)) as cursor:
                row = await cursor.fetchone()
                return json.loads(row[0]) if row else None

    async def cache_epic_details(self, slug: str, data: dict, permanent: bool = False):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO epic_app_cache (slug, fetched_at, data, permanent) VALUES (?, ?, ?, ?)",
                (slug, time.time(), json.dumps(data), 1 if permanent else 0),
            )
            await db.commit()

    async def get_cached_itch_details(self, url: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM itch_game_cache WHERE url = ?", (url,)) as cursor:
                row = await cursor.fetchone()
                return json.loads(row[0]) if row else None

    async def cache_itch_details(self, url: str, data: dict, permanent: bool = False):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO itch_game_cache (url, fetched_at, data, permanent) VALUES (?, ?, ?, ?)",
                (url, time.time(), json.dumps(data), 1 if permanent else 0),
            )
            await db.commit()

    async def get_cached_ps_details(self, url: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT data FROM ps_game_cache WHERE url = ?", (url,)) as cursor:
                row = await cursor.fetchone()
                return json.loads(row[0]) if row else None

    async def cache_ps_details(self, url: str, data: dict, permanent: bool = False):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO ps_game_cache (url, fetched_at, data, permanent) VALUES (?, ?, ?, ?)",
                (url, time.time(), json.dumps(data), 1 if permanent else 0),
            )
            await db.commit()
