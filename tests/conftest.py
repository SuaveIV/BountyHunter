import aiohttp
import pytest_asyncio
from dotenv import load_dotenv

from bounty_core.db.engine import Database
from bounty_core.store import Store

load_dotenv()


@pytest_asyncio.fixture
async def session():
    async with aiohttp.ClientSession() as session:
        yield session


@pytest_asyncio.fixture
async def store(tmp_path):
    # Use a temporary database file for tests
    db_path = tmp_path / "test_bounty.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    db = Database(db_url)
    store = Store(db)
    await store.setup()
    return store
