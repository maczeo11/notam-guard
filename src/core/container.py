"""Composition root.

Resolves every port to a concrete adapter, once per process. Tests call
`override()` to inject doubles; nothing else constructs an adapter directly.
"""
from typing import Any, Dict
import logging

from .config import get_settings
from .ports import (LLMPort, MemoryPort, NotamRepositoryPort, TicketPort, VectorStorePort)

log = logging.getLogger(__name__)

_instances: Dict[str, Any] = {}
_overrides: Dict[str, Any] = {}


def override(**ports: Any) -> None:
    """Inject test doubles, e.g. `override(vector_store=FakeStore())`."""
    _overrides.update(ports)


def reset() -> None:
    """Clear cached adapters and overrides — used between tests."""
    _instances.clear()
    _overrides.clear()


def _resolve(name: str, factory):
    if name in _overrides:
        return _overrides[name]
    if name not in _instances:
        _instances[name] = factory()
    return _instances[name]


def _redis_client():
    from src.adapters.redis_adapter import connect
    return _resolve("redis_client", connect)


def get_vector_store() -> VectorStorePort:
    def build():
        from src.adapters.pgvector_adapter import InMemoryVectorAdapter, PgVectorAdapter
        if get_settings().vector_adapter == "memory":
            return InMemoryVectorAdapter()
        return PgVectorAdapter()
    return _resolve("vector_store", build)


def get_memory() -> MemoryPort:
    def build():
        from src.adapters.redis_adapter import InMemoryMemoryAdapter, RedisMemoryAdapter
        client = _redis_client()
        return RedisMemoryAdapter(client) if client else InMemoryMemoryAdapter()
    return _resolve("memory", build)


def get_ticket_store() -> TicketPort:
    def build():
        from src.adapters.ticket_adapter import InMemoryTicketAdapter, RedisTicketAdapter
        client = _redis_client()
        return RedisTicketAdapter(client) if client else InMemoryTicketAdapter()
    return _resolve("ticket_store", build)


def get_notam_repository() -> NotamRepositoryPort:
    def build():
        from src.adapters.notam_repository import FileNotamRepository
        return FileNotamRepository()
    return _resolve("notam_repository", build)


def get_llm() -> LLMPort:
    def build():
        from src.adapters.llm_adapter import GroqLLMAdapter, OllamaLLMAdapter, RuleLLMAdapter
        adapter = get_settings().llm_adapter
        if adapter == "ollama":
            return OllamaLLMAdapter()
        if adapter == "groq":
            return GroqLLMAdapter()
        return RuleLLMAdapter()
    return _resolve("llm", build)
