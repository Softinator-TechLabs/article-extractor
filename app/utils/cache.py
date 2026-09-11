import time
from typing import Optional, Any
from app.config import settings

class URLCache:
    """A lightweight in-memory TTL cache for URL extraction results."""
    
    def __init__(self, ttl_seconds: int = settings.CACHE_TTL_SECONDS, max_entries: int = 1000):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries

    def get(self, url: str) -> Optional[Any]:
        if url in self._cache:
            timestamp, result = self._cache[url]
            if time.time() - timestamp < self._ttl:
                return result
            else:
                # Expired
                del self._cache[url]
        return None

    def set(self, url: str, result: Any):
        # We only cache successful requests with meaningful non-blank content
        content = getattr(result, "content", None)
        if content is not None and content.strip():
            self._cache[url] = (time.time(), result)
        
        # If cache exceeds max capacity, prune expired first; if still over, evict oldest
        if len(self._cache) > self._max_entries:
            self._cleanup()
            if len(self._cache) > self._max_entries:
                sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])
                excess = len(self._cache) - self._max_entries
                for k in sorted_keys[:excess]:
                    del self._cache[k]
            
    def clear(self) -> int:
        """Clear all entries in the cache and return the count of cleared items."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {
            "cached_entries": len(self._cache),
            "ttl_seconds": self._ttl,
            "max_entries": self._max_entries,
        }

    def _cleanup(self):
        now = time.time()
        keys_to_delete = [
            k for k, (ts, _) in self._cache.items() 
            if now - ts >= self._ttl
        ]
        for k in keys_to_delete:
            del self._cache[k]

# Global singleton cache instance
url_cache = URLCache()
