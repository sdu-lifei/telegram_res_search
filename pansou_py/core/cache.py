import json
import diskcache as dc
from typing import Optional, Any
from pansou_py.core.config import settings

class TwoLevelCache:
    def __init__(self):
        self.enabled = settings.CACHE_ENABLED
        self.ttl = settings.CACHE_TTL * 60  # convert minutes to seconds
        if self.enabled:
            # size_limit in bytes
            self.disk_cache = dc.Cache(settings.CACHE_PATH, size_limit=settings.CACHE_MAX_SIZE * 1024 * 1024)
        else:
            self.disk_cache = None

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled or not self.disk_cache:
            return None
        value = self.disk_cache.get(key)
        if value:
            try:
                # Assuming value is JSON serialized
                return json.loads(value)
            except:
                return value
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if not self.enabled or not self.disk_cache:
            return
        
        expire_time = ttl if ttl is not None else self.ttl
        try:
            if isinstance(value, (dict, list)):
                stored_value = json.dumps(value)
            elif hasattr(value, "model_dump_json"):
                stored_value = value.model_dump_json()
            else:
                stored_value = value
                
            self.disk_cache.set(key, stored_value, expire=expire_time)
        except Exception as e:
            print(f"Cache set error for {key}: {e}")

    def clear(self):
        if self.disk_cache:
            self.disk_cache.clear()

    def delete(self, key: str):
        if self.disk_cache:
            self.disk_cache.delete(key)

# Global cache instance
cache_service = TwoLevelCache()
