"""Lightweight in-memory TTL cache for DoD Budget tools.

Provides a simple TTLCache class for caching reference data, aggregations,
and other expensive queries with configurable expiry.
"""

import time
import threading
from typing import Any


class TTLCache:
    """Thread-safe in-memory cache with time-to-live (TTL) expiry.

    Entries expire after ``ttl_seconds`` seconds. A maximum of ``maxsize``
    entries are retained; when the cache is full the oldest entry is evicted.

    Usage::

        cache = TTLCache(maxsize=128, ttl_seconds=300)
        cache.set("my_key", {"data": [1, 2, 3]})
        value = cache.get("my_key")  # returns dict or None if expired/missing
    """

    def __init__(self, maxsize: int = 128, ttl_seconds: float = 300.0) -> None:
        """Initialise the cache.

        Args:
            maxsize: Maximum number of entries to store (default 128).
            ttl_seconds: Seconds before a cached entry expires (default 300).
        """
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        # Maps key -> (value, expires_at)
        self._store: dict[Any, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: Any) -> Any | None:
        """Return cached value for *key*, or ``None`` if absent or expired.

        Args:
            key: Cache key (must be hashable).

        Returns:
            Cached value, or ``None``.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: Any, value: Any) -> None:
        """Store *value* under *key* with the configured TTL.

        If the cache is full, the entry with the earliest expiry is evicted
        before inserting the new one.

        Args:
            key: Cache key (must be hashable).
            value: Value to cache (any type).
        """
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            if key not in self._store and len(self._store) >= self._maxsize:
                # Evict the entry that expires soonest
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]
            self._store[key] = (value, expires_at)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        """Return cache statistics.

        Returns:
            Dict with keys ``hits``, ``misses``, and ``size``.
        """
        with self._lock:
            # Purge expired entries before reporting size
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._store),
            }

    def delete(self, key: Any) -> None:
        """Remove a single entry from the cache.

        Args:
            key: Cache key to remove (no-op if not present).
        """
        with self._lock:
            self._store.pop(key, None)
