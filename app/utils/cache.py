import time
from typing import Optional, Any
from app.config import settings

class URLCache:
    """A lightweight in-memory TTL cache for URL extraction results."""
    
    def __init__(self, ttl_seconds: int = settings.CACHE_TTL_SECONDS):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds

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
        # We only cache successful requests
        if getattr(result, "content", None) is not None:
            self._cache[url] = (time.time(), result)
        
        # Simple cleanup heuristic to avoid unbound memory growth if running for months
        # If the cache gets too large, sweep expired entries
        if len(self._cache) > 1000:
            self._cleanup()
            
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
