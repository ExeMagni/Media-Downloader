import threading
import time


class ApplicationStateService:
    def __init__(self, cache_ttl_seconds: int = 300):
        self._lock = threading.RLock()
        self._last_results = []
        self._download_queue = []
        self._search_cache = {}
        self._cache_ttl_seconds = cache_ttl_seconds

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
            self._search_cache[key] = (time.time(), list(results or []))
