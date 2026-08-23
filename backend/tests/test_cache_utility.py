"""Unit tests for AsyncInMemoryCache utility and @cached decorator."""

import asyncio
import pytest
import pytest_asyncio

from src.utils.cache import AsyncInMemoryCache, cached


@pytest.mark.asyncio
async def test_cache_set_and_get():
    cache = AsyncInMemoryCache()
    await cache.set("test_key", {"data": 123}, ttl_seconds=60)

    val = await cache.get("test_key")
    assert val == {"data": 123}
    assert cache.size() == 1


@pytest.mark.asyncio
async def test_cache_ttl_expiration():
    cache = AsyncInMemoryCache()
    # Set 1 second TTL
    await cache.set("expire_key", "temp_value", ttl_seconds=1)

    assert await cache.get("expire_key") == "temp_value"
    await asyncio.sleep(1.1)
    # Should be expired and return None
    assert await cache.get("expire_key") is None
    assert cache.size() == 0


@pytest.mark.asyncio
async def test_cache_delete_and_clear():
    cache = AsyncInMemoryCache()
    await cache.set("k1", "v1")
    await cache.set("k2", "v2")
    assert cache.size() == 2

    assert await cache.delete("k1") is True
    assert await cache.delete("non_existent") is False
    assert await cache.get("k1") is None
    assert await cache.get("k2") == "v2"

    await cache.clear()
    assert cache.size() == 0


@pytest.mark.asyncio
async def test_cache_prefix_invalidation():
    cache = AsyncInMemoryCache()
    await cache.set("settings:active", {"lev": 20})
    await cache.set("settings:profile:1", {"risk": 2.0})
    await cache.set("watchlist:all", ["BTCUSDT", "ETHUSDT"])

    assert cache.size() == 3
    deleted_count = await cache.invalidate("settings")
    assert deleted_count == 2
    assert await cache.get("settings:active") is None
    assert await cache.get("settings:profile:1") is None
    assert await cache.get("watchlist:all") == ["BTCUSDT", "ETHUSDT"]
    assert cache.size() == 1


@pytest.mark.asyncio
async def test_cached_decorator():
    call_count = 0

    @cached(prefix="test_fn", ttl_seconds=60)
    async def expensive_computation(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    res1 = await expensive_computation(5)
    assert res1 == 10
    assert call_count == 1

    # Second call with same arg should hit cache
    res2 = await expensive_computation(5)
    assert res2 == 10
    assert call_count == 1

    # Different arg should compute and increment count
    res3 = await expensive_computation(10)
    assert res3 == 20
    assert call_count == 2
