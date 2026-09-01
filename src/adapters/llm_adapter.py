"""LLM adapters.

The LLM routes the request and renders the operator-facing sentence. It never
decides ALLOW/BLOCK — that comes from `tools.validate_flight`. Every adapter
degrades to the deterministic rule adapter rather than failing the request.
"""
from typing import List
import logging

from src.core.config import get_settings
from src.core.domain import Action
from src.core.ports import LLMPort

log = logging.getLogger(__name__)

_ROUTE_PROMPT = (
    "You route requests for a drone airspace compliance gate.\n"
    "Reply with exactly one word: retrieve, act, or both.\n"
    "  retrieve - the request asks about regulations or NOTAMs and carries no coordinates\n"
    "  act      - the request is a flight plan with coordinates and no regulatory question\n"
    "  both     - the request carries coordinates AND asks about a rule or NOTAM\n"
    "Request: {query}\nHas coordinates: {has_coords}\nAnswer:"
)


class RuleLLMAdapter(LLMPort):
    """Deterministic baseline. Also the fallback for every other adapter, so the
    service has no hard dependency on an LLM provider being reachable."""

    _REGULATORY = ("notam", "crane", "dgca", "car", "rule", "regulation", "allowed", "§")

    def route(self, query: str, has_coords: bool) -> str:
        lowered = query.lower()
        mentions_rule = any(term in lowered for term in self._REGULATORY)
        if has_coords and mentions_rule:
            return Action.BOTH.value
        if has_coords:
            return Action.ACT.value
        return Action.RETRIEVE.value

    def respond(self, verdict: str, reason: str, citations: List[str]) -> str:
        refs = ", ".join(citations) if citations else "no supporting citation"
        return f"{verdict}: {reason} [{refs}]"


class _ChatModelAdapter(LLMPort):
    """Shared behaviour for chat-model backends: one prompt each for routing and
    rendering, and a rule-adapter fallback on any provider error."""

    def __init__(self):
        self._fallback = RuleLLMAdapter()
        self._llm = None

    @property
    def available(self) -> bool:
        return self._llm is not None

    def route(self, query: str, has_coords: bool) -> str:
        if not self.available:
            return self._fallback.route(query, has_coords)
        try:
            raw = self._llm.invoke(
                _ROUTE_PROMPT.format(query=query, has_coords=has_coords)).content.lower()
        except Exception as exc:
            log.warning("router LLM failed (%s) — falling back to rules", exc)
            return self._fallback.route(query, has_coords)
        for action in (Action.BOTH, Action.ACT, Action.RETRIEVE):
            if action.value in raw:
                return action.value
        log.warning("router LLM returned unparsable %r — falling back to rules", raw[:80])
        return self._fallback.route(query, has_coords)

    def respond(self, verdict: str, reason: str, citations: List[str]) -> str:
        if not self.available:
            return self._fallback.respond(verdict, reason, citations)
        prompt = (
            "Write one sentence for a drone operator. State the verdict and the reason "
            "exactly as given; cite the references verbatim; add nothing else.\n"
            f"Verdict: {verdict}\nReason: {reason}\nReferences: {', '.join(citations) or 'none'}"
        )
        try:
            return self._llm.invoke(prompt).content.strip()
        except Exception as exc:
            log.warning("responder LLM failed (%s) — falling back to rules", exc)
            return self._fallback.respond(verdict, reason, citations)


class GroqLLMAdapter(_ChatModelAdapter):
    def __init__(self):
        super().__init__()
        settings = get_settings()
        try:
            from langchain_groq import ChatGroq
            self._llm = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key,
                                 temperature=0)
        except Exception as exc:
            log.warning("Groq unavailable (%s) — using rule adapter", exc)


class OllamaLLMAdapter(_ChatModelAdapter):
    def __init__(self):
        super().__init__()
        try:
            from langchain_ollama import ChatOllama
            self._llm = ChatOllama(model=get_settings().ollama_model, temperature=0)
        except Exception as exc:
            log.warning("Ollama unavailable (%s) — using rule adapter", exc)
