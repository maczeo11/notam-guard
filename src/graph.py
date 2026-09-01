"""The decision graph.

    router ─┬─ retrieve ─→ retriever ─────────────→ safety → responder → END
            ├─ act ──────────────────→ validator ─→ safety → responder → END
            └─ both ────→ retriever ─→ validator ─→ safety → responder → END

The router's choice is a real branch, taken through `add_conditional_edges` —
not a value computed and then ignored. The verdict is produced by `safety`, which
runs before `responder`, so the LLM renders a decision it cannot influence.
"""
from typing import List, TypedDict
import logging
import time

from src.core import container
from src.core.citations import ground
from src.core.config import get_settings
from src.core.domain import Action, Citation, Decision, FlightPlan, Verdict
from src.core.errors import NotamSourceUnavailable, RetrievalUnavailable
from src.core.safety import finalise
from src.core.tracing import traced
from src.tools import validate_flight

log = logging.getLogger(__name__)


class State(TypedDict, total=False):
    # Request
    query: str
    lat: float
    lon: float
    alt: int
    drone_id: str
    #: Evaluation instant, so a scored run does not depend on the wall clock.
    at: object
    # Routing
    action: str
    # Evidence
    retrieved: List[str]
    retrieval_failed: bool
    validated: bool
    violation: bool
    refs: List[str]
    citations: List[Citation]
    advisories: List[str]
    warnings: List[str]
    # Outcome
    verdict: str
    reason: str
    narrative: str
    confidence: float
    requires_human: bool
    ticket_id: str
    ticket_deduped: bool
    history: List[str]
    latency_ms: dict


def _flight_plan(state: State) -> FlightPlan:
    return FlightPlan(lat=state["lat"], lon=state["lon"], alt=state["alt"],
                      drone_id=state["drone_id"], query=state.get("query", ""),
                      at=state.get("at"))


def _record_latency(state: State, stage: str, started: float) -> dict:
    latencies = dict(state.get("latency_ms") or {})
    latencies[stage] = round((time.perf_counter() - started) * 1000, 1)
    return latencies


@traced("router")
def router(state: State) -> dict:
    started = time.perf_counter()
    has_coords = state.get("lat") is not None and state.get("lon") is not None
    action = container.get_llm().route(state.get("query", ""), has_coords)
    log.info("router chose %s for drone=%s", action, state.get("drone_id"))
    return {"action": action, "latency_ms": _record_latency(state, "router", started)}


@traced("retriever")
def retriever(state: State) -> dict:
    started = time.perf_counter()
    try:
        chunks = container.get_vector_store().search(
            state.get("query", ""), k=get_settings().retrieval_k)
    except RetrievalUnavailable as exc:
        # Fail closed: no fabricated chunks, no ALLOW built on them.
        log.error("retrieval unavailable: %s", exc)
        return {"retrieved": [], "retrieval_failed": True,
                "latency_ms": _record_latency(state, "retriever", started)}
    return {"retrieved": chunks, "retrieval_failed": False,
            "latency_ms": _record_latency(state, "retriever", started)}


@traced("validator")
def validator(state: State) -> dict:
    started = time.perf_counter()
    plan = _flight_plan(state)
    try:
        notams = container.get_notam_repository().active(plan.when())
    except NotamSourceUnavailable as exc:
        log.error("NOTAM source unavailable: %s", exc)
        return {"validated": False, "violation": False, "refs": [], "advisories": [],
                "warnings": [f"NOTAM corpus unavailable ({exc}) — airspace not assessed"],
                "latency_ms": _record_latency(state, "validator", started)}

    result = validate_flight(plan, notams)
    return {
        "validated": True,
        "violation": result.violation,
        "refs": result.refs,
        "reason": result.reason,
        "advisories": result.advisories,
        "warnings": result.warnings,
        "latency_ms": _record_latency(state, "validator", started),
    }


@traced("safety")
def safety(state: State) -> dict:
    """Grounds the citations, applies the safety policy, and opens a ticket for
    anything a human has to look at."""
    started = time.perf_counter()
    warnings = list(state.get("warnings") or [])
    retrieved = state.get("retrieved") or []

    if not state.get("validated") and not state.get("retrieval_failed"):
        warnings.append("no flight plan was validated on this route — nothing cleared")
    if state.get("action") == Action.ACT.value and not retrieved:
        warnings.append("verdict not cross-checked against the retrieved corpus (route=act)")

    citations = ground(state.get("refs") or [], retrieved) if retrieved else []
    outcome = finalise(
        violation=bool(state.get("violation")),
        citations=citations,
        warnings=warnings,
        retrieval_failed=bool(state.get("retrieval_failed")),
    )

    update: dict = {
        "verdict": outcome.verdict.value,
        "confidence": outcome.confidence,
        "requires_human": outcome.requires_human,
        "citations": citations,
        "warnings": outcome.warnings,
        "ticket_id": "",
        "ticket_deduped": False,
    }
    if not state.get("validated"):
        update["reason"] = state.get("reason") or "no flight plan evaluated"
    if outcome.verdict is Verdict.HOLD and state.get("retrieval_failed"):
        update["reason"] = "retrieval unavailable — cannot verify airspace, holding flight"

    if outcome.requires_human:
        ticket = container.get_ticket_store().create(
            issue=update.get("reason") or state.get("reason", ""),
            severity="HIGH" if outcome.verdict is Verdict.BLOCK else "MEDIUM",
            drone_id=state["drone_id"],
            notam_id=next((c.ref for c in citations), None),
        )
        update["ticket_id"] = ticket.ticket_id
        update["ticket_deduped"] = ticket.deduped
        if not ticket.deduped:
            memory = container.get_memory()
            update["history"] = memory.push_history(state["drone_id"], ticket.ticket_id)
            memory.add_tile(state["lat"], state["lon"], state["drone_id"])

    update["latency_ms"] = _record_latency(state, "safety", started)
    return update


@traced("responder")
def responder(state: State) -> dict:
    """Renders the operator-facing sentence. Cannot change the verdict."""
    started = time.perf_counter()
    refs = [c.ref for c in state.get("citations") or []]
    text = container.get_llm().respond(state["verdict"], state.get("reason", ""), refs)
    return {"reason": state.get("reason", ""), "narrative": text,
            "latency_ms": _record_latency(state, "responder", started)}


def _after_router(state: State) -> str:
    action = state.get("action", Action.BOTH.value)
    return "retriever" if action in (Action.RETRIEVE.value, Action.BOTH.value) else "validator"


def _after_retriever(state: State) -> str:
    return "validator" if state.get("action") == Action.BOTH.value else "safety"


def build_graph():
    """Compile the LangGraph state machine.

    An ImportError falls back to an equivalent sequential runner so the eval and
    tests run without the dependency; any other error is a real bug and is raised.
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        log.warning("langgraph not installed — using the sequential fallback runner")
        return _SequentialGraph()

    builder = StateGraph(State)
    for name, node in (("router", router), ("retriever", retriever),
                       ("validator", validator), ("safety", safety), ("responder", responder)):
        builder.add_node(name, node)

    builder.set_entry_point("router")
    builder.add_conditional_edges("router", _after_router,
                                  {"retriever": "retriever", "validator": "validator"})
    builder.add_conditional_edges("retriever", _after_retriever,
                                  {"validator": "validator", "safety": "safety"})
    builder.add_edge("validator", "safety")
    builder.add_edge("safety", "responder")
    builder.add_edge("responder", END)
    return builder.compile()


class _SequentialGraph:
    """Mirrors the compiled graph's branching, for environments without LangGraph."""

    def invoke(self, state: State) -> State:
        state = {**state, **router(state)}
        if _after_router(state) == "retriever":
            state = {**state, **retriever(state)}
            if _after_retriever(state) == "validator":
                state = {**state, **validator(state)}
        else:
            state = {**state, **validator(state)}
        state = {**state, **safety(state)}
        state = {**state, **responder(state)}
        return state


def initial_state(plan: FlightPlan) -> State:
    return State(query=plan.query, lat=plan.lat, lon=plan.lon, alt=plan.alt,
                 drone_id=plan.drone_id, at=plan.at, retrieved=[], refs=[], citations=[],
                 advisories=[], warnings=[], latency_ms={})


def to_decision(state: State) -> Decision:
    return Decision(
        verdict=Verdict(state["verdict"]),
        reason=state.get("narrative") or state.get("reason", ""),
        confidence=state.get("confidence", 0.0),
        citations=state.get("citations") or [],
        retrieved=state.get("retrieved") or [],
        advisories=state.get("advisories") or [],
        warnings=state.get("warnings") or [],
        requires_human=bool(state.get("requires_human")),
        ticket_id=state.get("ticket_id", ""),
        action=Action(state.get("action", Action.BOTH.value)),
    )


def decide(plan: FlightPlan, compiled=None) -> Decision:
    """Run one flight plan through the graph and return the final decision."""
    runner = compiled or get_graph()
    return to_decision(runner.invoke(initial_state(plan)))


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
