from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .models import Base


class Database:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker | None = None

    async def connect(self):
        """Initializes the database connection and creates tables."""
        # Using aiosqlite driver
        # Ensure the URL is formatted correctly (e.g. sqlite+aiosqlite:///file.db)
        if "sqlite" in self.db_url and "aiosqlite" not in self.db_url:
            # Auto-fix common config issue
            self.db_url = self.db_url.replace("sqlite://", "sqlite+aiosqlite://")

        self.engine = create_async_engine(self.db_url, echo=False)

        # SQLite specific optimizations
        if "sqlite" in self.db_url:

            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self):
        if self.engine:
            await self.engine.dispose()

    @property
    def session(self):
        """Returns a new session context manager."""
        if not self.session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.session_factory()
