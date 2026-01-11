import pytest
import pytest_asyncio

from bounty_core.db.engine import Database
from bounty_core.store import Store


@pytest_asyncio.fixture
async def memory_store():
    # Use in-memory SQLite for fast testing
    db = Database("sqlite+aiosqlite:///:memory:")
    store = Store(db)
    await store.setup()
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_store_seen_posts(memory_store: Store):
    post_id = "test_post_1"

    # Initially unseen
    assert await memory_store.is_post_seen(post_id) is False

    # Mark as seen
    await memory_store.mark_post_seen(post_id)
    assert await memory_store.is_post_seen(post_id) is True

    # Marking again should be safe (idempotent)
    await memory_store.mark_post_seen(post_id)
    assert await memory_store.is_post_seen(post_id) is True


@pytest.mark.asyncio
async def test_store_subscriptions(memory_store: Store):
    guild_id = 123
    channel_id = 456
    role_id = 789

    # No subs initially
    subs = await memory_store.get_subscriptions()
    assert len(subs) == 0

    # Add sub
    await memory_store.add_subscription(guild_id, channel_id, role_id)
    subs = await memory_store.get_subscriptions()
    assert len(subs) == 1
    assert subs[0] == (guild_id, channel_id, role_id)

    # Update sub (change role)
    await memory_store.add_subscription(guild_id, channel_id, None)
    subs = await memory_store.get_subscriptions()
    assert len(subs) == 1
    assert subs[0] == (guild_id, channel_id, None)

    # Remove sub
    await memory_store.remove_subscription(guild_id, channel_id)
    subs = await memory_store.get_subscriptions()
    assert len(subs) == 0


@pytest.mark.asyncio
async def test_store_game_cache(memory_store: Store):
    store_name = "test_store"
    game_id = "game_1"
    data = {"name": "Test Game", "price": 0}

    # Initially empty
    cached = await memory_store.get_cached_details(store_name, game_id)
    assert cached is None

    # Cache it
    await memory_store.cache_details(store_name, game_id, data)

    # Retrieve it
    cached = await memory_store.get_cached_details(store_name, game_id)
    assert cached is not None
    assert cached["name"] == "Test Game"
    assert cached["price"] == 0

    # Update it
    data["price"] = 10
    await memory_store.cache_details(store_name, game_id, data)
    cached = await memory_store.get_cached_details(store_name, game_id)
    assert cached["price"] == 10

    # Clear cache
    await memory_store.clear_cache()
    cached = await memory_store.get_cached_details(store_name, game_id)
    assert cached is None
