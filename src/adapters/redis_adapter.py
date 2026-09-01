"""Redis-backed fleet memory, with an in-process fallback.

`src/memory.py` previously held a second, independent Redis implementation that
rebound module-level functions at import time. Both now live here behind
`MemoryPort`, so there is one code path and it is injectable.
"""
from typing import List, Optional
import logging
import threading

from src.core.config import get_settings
from src.core.ports import MemoryPort

log = logging.getLogger(__name__)

#: ~110m at the equator — the resolution of the "has this tile been cleared" memory.
TILE_PRECISION = 3


def tile_key(lat: float, lon: float) -> str:
    return f"tile:{round(lat, TILE_PRECISION)},{round(lon, TILE_PRECISION)}"


def connect():
    """Return a live Redis client, or None if Redis is unreachable.

    Fleet memory is an optimisation, not a safety control, so degrading to
    in-process storage is acceptable here — unlike retrieval, which must fail closed.
    """
    settings = get_settings()
    try:
        import redis
        client = redis.from_url(settings.redis_url,
                                socket_connect_timeout=settings.redis_connect_timeout)
        client.ping()
        return client
    except Exception as exc:
        log.warning("Redis unavailable at %s (%s) — using in-process memory",
                    settings.redis_url, exc)
        return None


def _decode(values) -> List[str]:
    return [v.decode() if isinstance(v, bytes) else v for v in values]


class RedisMemoryAdapter(MemoryPort):
    def __init__(self, client):
        self._r = client
        self._limit = get_settings().history_length

    def push_history(self, drone_id: str, ticket_id: str) -> List[str]:
        key = f"drone:{drone_id}:history"
        pipe = self._r.pipeline()
        pipe.lpush(key, ticket_id)
        pipe.ltrim(key, 0, self._limit - 1)
        pipe.lrange(key, 0, self._limit - 1)
        return _decode(pipe.execute()[-1])

    def get_history(self, drone_id: str) -> List[str]:
        return _decode(self._r.lrange(f"drone:{drone_id}:history", 0, self._limit - 1))

    def add_tile(self, lat: float, lon: float, drone_id: str) -> str:
        key = tile_key(lat, lon)
        self._r.set(key, drone_id, ex=get_settings().ticket_ttl_seconds)
        self._r.geoadd("fleet:tiles", (lon, lat, drone_id))
        return key

    def get_tile(self, lat: float, lon: float) -> Optional[str]:
        value = self._r.get(tile_key(lat, lon))
        return value.decode() if isinstance(value, bytes) else value


class InMemoryMemoryAdapter(MemoryPort):
    def __init__(self):
        self._lock = threading.Lock()
        self._history: dict[str, List[str]] = {}
        self._tiles: dict[str, str] = {}
        self._limit = get_settings().history_length

    def push_history(self, drone_id: str, ticket_id: str) -> List[str]:
        with self._lock:
            entries = self._history.setdefault(drone_id, [])
            entries.insert(0, ticket_id)
            del entries[self._limit:]
            return list(entries)

    def get_history(self, drone_id: str) -> List[str]:
        with self._lock:
            return list(self._history.get(drone_id, []))

    def add_tile(self, lat: float, lon: float, drone_id: str) -> str:
        key = tile_key(lat, lon)
        with self._lock:
            self._tiles[key] = drone_id
        return key

    def get_tile(self, lat: float, lon: float) -> Optional[str]:
        with self._lock:
            return self._tiles.get(tile_key(lat, lon))
