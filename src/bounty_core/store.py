import aiosqlite
import os
from typing import Optional, List, Tuple

CREATE_SEEN_TABLE = """
CREATE TABLE IF NOT EXISTS seen_posts (
  uri TEXT PRIMARY KEY,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SUBS_TABLE = """
CREATE TABLE IF NOT EXISTS subscriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  UNIQUE(guild_id, channel_id)
);
"""

class Store:
    def __init__(self, db_path: str = "./data/bountyhunter.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute(CREATE_SEEN_TABLE)
        await self._conn.execute(CREATE_SUBS_TABLE)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def seen(self, uri: str) -> bool:
        cur = await self._conn.execute("SELECT 1 FROM seen_posts WHERE uri = ? LIMIT 1", (uri,))
        row = await cur.fetchone()
        await cur.close()
        return bool(row)

    async def mark_seen(self, uri: str):
        await self._conn.execute("INSERT OR IGNORE INTO seen_posts(uri) VALUES(?)", (uri,))
        await self._conn.commit()

    # Subscriptions (per-server)
    async def add_subscription(self, guild_id: str, channel_id: str):
        await self._conn.execute(
            "INSERT OR IGNORE INTO subscriptions (guild_id, channel_id) VALUES(?,?)",
            (str(guild_id), str(channel_id)),
        )
        await self._conn.commit()

    async def remove_subscription(self, guild_id: str, channel_id: str):
        await self._conn.execute(
            "DELETE FROM subscriptions WHERE guild_id = ? AND channel_id = ?", (str(guild_id), str(channel_id))
        )
        await self._conn.commit()

    async def list_subscriptions(self) -> List[Tuple[str, str]]:
        cur = await self._conn.execute("SELECT guild_id, channel_id FROM subscriptions")
        rows = await cur.fetchall()
        await cur.close()
        return rows

    async def list_subscriptions_for_guild(self, guild_id: str) -> List[str]:
        cur = await self._conn.execute("SELECT channel_id FROM subscriptions WHERE guild_id = ?", (str(guild_id),))
        rows = await cur.fetchall()
        await cur.close()
        return [r[0] for r in rows]