"""High-performance in-memory asynchronous cache with TTL and key prefix invalidation."""

import asyncio
import functools
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


class CacheEntry:
    """Represents a cached value with an optional expiration timestamp."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: Optional[float] = None) -> None:
        self.value = value
        self.expires_at = expires_at

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class AsyncInMemoryCache:
    """Thread-safe and coroutine-safe in-memory cache for FastAPI endpoints and services."""

    def __init__(self) -> None:
        self._store: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache if present and not expired."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.is_expired:
                del self._store[key]
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Store a value in the cache with an optional TTL in seconds."""
        expires_at = time.time() + ttl_seconds if ttl_seconds is not None else None
        async with self._lock:
            self._store[key] = CacheEntry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> bool:
        """Delete a single key from the cache. Returns True if deleted, False if not found."""
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def invalidate(self, prefix: str) -> int:
        """Invalidate all keys starting with the given prefix. Returns count of deleted keys."""
        async with self._lock:
            keys_to_delete: List[str] = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)

    async def clear(self) -> None:
        """Clear the entire cache."""
        async with self._lock:
            self._store.clear()

    def size(self) -> int:
        """Return the current number of cached items."""
        return len(self._store)


# Global singleton cache instance
in_memory_cache = AsyncInMemoryCache()


def cached(prefix: str, ttl_seconds: int = 60, key_builder: Optional[Callable[..., str]] = None) -> Callable:
    """Decorator to cache asynchronous function/endpoint results using AsyncInMemoryCache."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if key_builder:
                cache_key = f"{prefix}:{key_builder(*args, **kwargs)}"
            else:
                # Default key formatting
                args_str = "_".join(str(a) for a in args if not hasattr(a, "__dict__"))
                kwargs_str = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()) if not hasattr(v, "__dict__"))
                cache_key = f"{prefix}:{args_str}:{kwargs_str}".strip(":")

            cached_val = await in_memory_cache.get(cache_key)
            if cached_val is not None:
                return cached_val

            result = await func(*args, **kwargs)
            if result is not None:
                await in_memory_cache.set(cache_key, result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator
