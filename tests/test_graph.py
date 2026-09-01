"""End-to-end behaviour of the decision graph.

These cover the two claims that the old code could not support: that the router
actually branches, and that a broken retriever holds the flight instead of
clearing it against invented evidence.
"""
from typing import List

import pytest

from src.core import container
from src.core.domain import Action, FlightPlan, Verdict
from src.core.errors import RetrievalUnavailable
from src.core.ports import VectorStorePort
from src.graph import build_graph, decide
from tests.conftest import NOW


class BrokenVectorStore(VectorStorePort):
    def search(self, query: str, k: int = 3) -> List[str]:
        raise RetrievalUnavailable("database is down")


class IrrelevantVectorStore(VectorStorePort):
    """Retrieves successfully, but nothing that supports the verdict."""

    def search(self, query: str, k: int = 3) -> List[str]:
        return ["§12 Battery safety: swap if RUL <20 cycles and temp >35C."]


@pytest.fixture
def graph():
    return build_graph()


def plan(lat=18.53, lon=73.84, alt=120, drone_id="D12", query=None):
    return FlightPlan(
        lat=lat, lon=lon, alt=alt, drone_id=drone_id, at=NOW,
        query=query or "check crane NOTAM and DGCA CAR limits for this flight")


def test_regulatory_query_with_coordinates_routes_through_both_nodes(wired, graph):
    decision = decide(plan(), graph)
    assert decision.action is Action.BOTH
    assert decision.retrieved, "the both-route must actually retrieve"


def test_plain_flight_plan_routes_to_act_and_skips_retrieval(wired, graph):
    decision = decide(plan(alt=80, query="D40 telemetry check"), graph)
    assert decision.action is Action.ACT
    assert decision.retrieved == []


def test_act_route_holds_because_nothing_was_cross_checked(wired, graph):
    """Geometry alone clears this flight, but no regulation was consulted, so
    the gate holds rather than issuing an unverified ALLOW."""
    decision = decide(plan(alt=80, query="D40 telemetry check"), graph)
    assert decision.verdict is Verdict.HOLD
    assert decision.requires_human


def test_breach_produces_a_block_with_a_grounded_citation(wired, graph):
    decision = decide(plan(alt=120), graph)
    assert decision.verdict is Verdict.BLOCK
    assert [c.ref for c in decision.citations] == ["NOTAM 09/03"]
    assert all(c.grounded for c in decision.citations)
    assert decision.requires_human


def test_clear_flight_is_allowed_without_a_human(wired, graph):
    decision = decide(plan(alt=80), graph)
    assert decision.verdict is Verdict.ALLOW
    assert decision.requires_human is False


def test_retrieval_failure_holds_the_flight_and_never_allows(wired, graph):
    """The old adapter answered a dead database with hardcoded chunks, so this
    same flight came back ALLOW with fabricated citations."""
    container.override(vector_store=BrokenVectorStore())
    decision = decide(plan(alt=80), graph)
    assert decision.verdict is Verdict.HOLD
    assert decision.requires_human
    assert decision.citations == []
    assert any("retrieval unavailable" in w for w in decision.warnings)


def test_retrieval_failure_on_a_breach_still_blocks(wired, graph):
    container.override(vector_store=BrokenVectorStore())
    assert decide(plan(alt=120), graph).verdict is not Verdict.ALLOW


def test_unsupported_citation_downgrades_the_allow_to_a_hold(wired, graph):
    """Retrieval works but returns an unrelated clause, so 'CAR §7' cannot be
    shown — the grounding check fires and the flight is held."""
    container.override(vector_store=IrrelevantVectorStore())
    decision = decide(plan(alt=80), graph)
    assert decision.verdict is Verdict.HOLD
    assert any(not c.grounded for c in decision.citations)


def test_a_held_flight_opens_exactly_one_ticket_for_repeated_requests(wired, graph):
    first = decide(plan(alt=120), graph)
    second = decide(plan(alt=120), graph)
    assert first.ticket_id
    assert first.ticket_id == second.ticket_id


def test_an_allowed_flight_opens_no_ticket(wired, graph):
    assert decide(plan(alt=80), graph).ticket_id == ""


def test_ticket_is_recorded_in_fleet_memory(wired, graph):
    decision = decide(plan(alt=120), graph)
    assert decision.ticket_id in container.get_memory().get_history("D12")


def test_advisory_notam_is_surfaced_without_blocking(wired, graph):
    decision = decide(plan(lat=18.55, lon=73.86, alt=90), graph)
    assert decision.verdict is Verdict.ALLOW
    assert any("09/05" in a for a in decision.advisories)


def test_unevaluable_notam_is_reported_on_every_decision(wired, graph):
    decision = decide(plan(alt=80), graph)
    assert any("09/04" in w for w in decision.warnings)
    assert decision.confidence < 1.0
