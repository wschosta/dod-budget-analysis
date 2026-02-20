"""Tests for utils/cache.py — lightweight TTL cache."""
import time
from utils.cache import TTLCache


class TestTTLCache:
    def test_basic_set_get(self):
        cache = TTLCache()
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_miss_returns_none(self):
        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("key", "value")
        assert cache.get("key") == "value"
        time.sleep(0.1)
        assert cache.get("key") is None

    def test_clear(self):
        cache = TTLCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None

    def test_stats_tracks_hits_misses(self):
        cache = TTLCache()
        cache.set("k", "v")
        cache.get("k")   # hit
        cache.get("nope") # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_stats_size(self):
        cache = TTLCache()
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.stats()["size"] == 2

    def test_maxsize_eviction(self):
        cache = TTLCache(maxsize=2)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")  # should evict one
        # At most 2 entries remain
        vals = [cache.get(k) for k in ("k1", "k2", "k3")]
        present = [v for v in vals if v is not None]
        assert len(present) <= 2

    def test_overwrite_existing(self):
        cache = TTLCache()
        cache.set("k", "old")
        cache.set("k", "new")
        assert cache.get("k") == "new"

    def test_delete(self):
        cache = TTLCache()
        cache.set("k", "v")
        cache.delete("k")
        assert cache.get("k") is None

    def test_delete_nonexistent_no_error(self):
        cache = TTLCache()
        cache.delete("nope")  # should not raise

    def test_stats_resets_after_clear(self):
        cache = TTLCache()
        cache.set("k", "v")
        cache.get("k")
        cache.clear()
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

    def test_thread_safety(self):
        import threading
        cache = TTLCache(maxsize=100)
        errors = []
        def worker():
            try:
                for i in range(50):
                    cache.set(f"k{i}", i)
                    cache.get(f"k{i}")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
