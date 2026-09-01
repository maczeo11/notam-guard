"""Hex DI — 4 ports, ABC + DI valid for swappable without overkill (PRAJNA-style)"""
import os
from .ports import VectorStorePort, MemoryPort, LLMPort

def get_vector_store() -> VectorStorePort:
    use = os.getenv("VECTOR_ADAPTER", "pgvector")
    if use == "memory":
        from src.adapters.pgvector_adapter import InMemoryVectorAdapter
        return InMemoryVectorAdapter()
    from src.adapters.pgvector_adapter import PgVectorAdapter
    return PgVectorAdapter()

def get_memory() -> MemoryPort:
    from src.adapters.redis_adapter import RedisAdapter
    return RedisAdapter()

def get_llm() -> LLMPort:
    use = os.getenv("LLM_ADAPTER", "groq" if os.getenv("GROQ_API_KEY") else "rule")
    if use == "ollama":
        from src.adapters.llm_adapter import OllamaLLMAdapter
        return OllamaLLMAdapter()
    if use == "groq":
        from src.adapters.llm_adapter import GroqLLMAdapter
        return GroqLLMAdapter()
    from src.adapters.llm_adapter import RuleLLMAdapter
    return RuleLLMAdapter()
