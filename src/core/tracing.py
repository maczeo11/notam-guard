"""LangSmith tracing.

`@traced` is a real `langsmith.traceable` when tracing is configured and a no-op
otherwise, so the graph carries observability without depending on it. The
previous code imported `traceable` and then discarded it, so nothing was traced.
"""
from typing import Callable, TypeVar
import logging

from .config import get_settings

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


def _noop(name: str) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        return fn
    return decorator


def _resolve():
    settings = get_settings()
    if not settings.tracing_enabled:
        return _noop

    key = settings.tracing_api_key
    if not key or key.startswith("lsv2_...") or "..." in key:
        # A placeholder copied from .env.example fails with a 403 on every
        # request. Say so once here instead of once per span.
        log.warning("tracing is enabled but LANGSMITH_API_KEY looks unset or is a "
                    "placeholder — traces will be rejected; get a key at "
                    "https://smith.langchain.com/settings")
        return _noop

    try:
        from langsmith import traceable
    except ImportError:
        log.warning("tracing is enabled but langsmith is not installed")
        return _noop

    def decorator(name: str):
        return traceable(name=name, run_type="chain")
    return decorator


_factory = None


def traced(name: str):
    """Decorate a graph node so it appears as a span in the LangSmith trace."""
    global _factory
    if _factory is None:
        _factory = _resolve()
    return _factory(name)
