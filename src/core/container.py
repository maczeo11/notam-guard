"""Hex DI — only 3 ports, valid for testability without overkill (PRAJNA-style)"""
import os
from .ports import VectorStorePort, MemoryPort

def get_vector_store() -> VectorStorePort:
    use = os.getenv("VECTOR_ADAPTER", "pgvector")
    if use == "memory":
        from src.adapters.pgvector_adapter import InMemoryVectorAdapter
        return InMemoryVectorAdapter()
    from src.adapters.pgvector_adapter import PgVectorAdapter
    return PgVectorAdapter()

def get_memory() -> MemoryPort:
    # RedisAdapter already falls back to in-mem, so single impl is enough
    from src.adapters.redis_adapter import RedisAdapter
    return RedisAdapter()
