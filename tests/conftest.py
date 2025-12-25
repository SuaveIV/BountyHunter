import aiohttp
import pytest_asyncio
from dotenv import load_dotenv

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
    store = Store(str(db_path))
    await store.setup()
    return store
