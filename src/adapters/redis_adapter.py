import os
from typing import List
from src.core.ports import MemoryPort
_mem = {}

class RedisAdapter(MemoryPort):
    def __init__(self):
        try:
            import redis
            self.r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=1)
            self.r.ping()
            self.ok = True
        except: self.ok = False
    def push(self, drone_id: str, ticket_id: str) -> List[str]:
        if self.ok:
            k=f"drone:{drone_id}:history"; self.r.lpush(k,ticket_id); self.r.ltrim(k,0,4); return [x.decode() if isinstance(x,bytes) else x for x in self.r.lrange(k,0,4)]
        lst=_mem.get(drone_id,[]); lst.insert(0,ticket_id); _mem[drone_id]=lst[:5]; return lst[:5]
    def get(self, drone_id: str) -> List[str]:
        if self.ok:
            return [x.decode() if isinstance(x,bytes) else x for x in self.r.lrange(f"drone:{drone_id}:history",0,4)]
        return _mem.get(drone_id,[])
