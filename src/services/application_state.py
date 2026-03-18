import threading
import time


class ApplicationStateService:
    def __init__(self, cache_ttl_seconds: int = 300, max_cache_entries: int = 200):
        self._lock = threading.RLock()
        self._last_results = []
        self._download_queue = []
        self._search_cache = {}
        self._cache_ttl_seconds = cache_ttl_seconds
        self._max_cache_entries = max(1, int(max_cache_entries))

    def _prune_search_cache_locked(self, now=None):
        now_ts = now if now is not None else time.time()
        expired_keys = []
        for key, (ts, _) in self._search_cache.items():
            if now_ts - ts >= self._cache_ttl_seconds:
                expired_keys.append(key)
        for key in expired_keys:
            self._search_cache.pop(key, None)

        overflow = len(self._search_cache) - self._max_cache_entries
        if overflow > 0:
            ordered = sorted(self._search_cache.items(),
                             key=lambda item: item[1][0])
            for key, _ in ordered[:overflow]:
                self._search_cache.pop(key, None)

    def get_last_results(self):
        with self._lock:
            return list(self._last_results)

    def set_last_results(self, results):
        with self._lock:
            self._last_results = list(results or [])

    def add_to_download_queue(self, item):
        with self._lock:
            self._download_queue.append(dict(item))

    def extend_download_queue(self, items):
        with self._lock:
            self._download_queue.extend(dict(item) for item in items)

    def remove_from_download_queue(self, queue_index: int):
        with self._lock:
            if queue_index < 0 or queue_index >= len(self._download_queue):
                return None
            return self._download_queue.pop(queue_index)

    def clear_download_queue(self):
        with self._lock:
            self._download_queue.clear()

    def get_download_queue_snapshot(self):
        with self._lock:
            return [dict(item) for item in self._download_queue]

    def get_download_queue_size(self):
        with self._lock:
            return len(self._download_queue)

    def get_cached_search(self, key: str):
        now = time.time()
        with self._lock:
            self._prune_search_cache_locked(now)
            cached = self._search_cache.get(key)
            if not cached:
                return None
            ts, results = cached
            if now - ts >= self._cache_ttl_seconds:
                self._search_cache.pop(key, None)
                return None
            return list(results)

    def set_cached_search(self, key: str, results):
        with self._lock:
            now = time.time()
            self._search_cache[key] = (now, list(results or []))
            self._prune_search_cache_locked(now)

    def clear_search_cache(self):
        with self._lock:
            removed = len(self._search_cache)
            self._search_cache.clear()
            return removed

    def get_search_cache_size(self):
        with self._lock:
            self._prune_search_cache_locked(time.time())
            return len(self._search_cache)

    def get_search_cache_size_bytes(self):
        import sys
        with self._lock:
            self._prune_search_cache_locked(time.time())
            total_bytes = 0
            for key, (ts, results) in self._search_cache.items():
                total_bytes += sys.getsizeof(key)
                total_bytes += sys.getsizeof(ts)
                total_bytes += sys.getsizeof(results)
                for item in results:
                    if isinstance(item, dict):
                        total_bytes += sys.getsizeof(item)
            return total_bytes
