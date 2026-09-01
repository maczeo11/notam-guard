import time
# Fallback in-mem if Redis not available — swap to redis.Redis later
_mem = {}

def push_history(drone_id: str, ticket_id: str):
    k = f"drone:{drone_id}:history"
    lst = _mem.get(k, [])
    lst.insert(0, ticket_id)
    _mem[k] = lst[:5]
    return lst[:5]

def get_history(drone_id: str):
    return _mem.get(f"drone:{drone_id}:history", [])

def geo_add_tile(lon: float, lat: float, drone_id: str):
    # mock tile 100m — keep simple, real uses Redis GEOADD
    tile = f"{round(lat,3)},{round(lon,3)}"
    _mem[f"tile:{tile}"] = drone_id
    return tile

# try real Redis if available
try:
    import redis
    import os
    _r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=1)
    _r.ping()
    # override with real
    def push_history(drone_id, ticket_id):  # type: ignore
        k = f"drone:{drone_id}:history"
        _r.lpush(k, ticket_id)
        _r.ltrim(k, 0, 4)
        return [x.decode() if isinstance(x, bytes) else x for x in _r.lrange(k, 0, 4)]
    def get_history(drone_id):  # type: ignore
        k = f"drone:{drone_id}:history"
        return [x.decode() if isinstance(x, bytes) else x for x in _r.lrange(k, 0, 4)]
except Exception:
    pass
