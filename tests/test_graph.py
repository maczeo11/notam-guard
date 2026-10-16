"""End-to-end behaviour of the decision graph.

These cover the two claims that the old code could not support: that the router
actually branches, and that a broken retriever holds the flight instead of
clearing it against invented evidence.
"""
from typing import List

import pytest

from src.adapters.llm_adapter import RuleLLMAdapter
from src.adapters.notam_repository import InMemoryNotamRepository
from src.core import container
from src.core.domain import Action, FlightPlan, Verdict
from src.core.errors import NotamSourceUnavailable, RetrievalUnavailable
from src.core.ports import NotamRepositoryPort, VectorStorePort
from src.graph import build_graph, decide
from tests.conftest import BIRDS, CRANE, NOW


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


class FixedRouteLLM(RuleLLMAdapter):
    """Stands in for an LLM router that answers with a fixed route."""

    def __init__(self, route: str):
        self._route = route

    def route(self, query: str, has_coords: bool) -> str:
        return self._route


class RecordingVectorStore(VectorStorePort):
    """Similarity search returns `chunks`; exact lookup returns `defined`."""

    def __init__(self, chunks: List[str], defined: List[str] | None = None):
        self.chunks = chunks
        self.defined = defined or []
        self.queries: List[str] = []
        self.lookups: List[List[str]] = []

    def search(self, query: str, k: int = 3) -> List[str]:
        self.queries.append(query)
        return self.chunks

    def lookup(self, refs):
        self.lookups.append(list(refs))
        return self.defined


class MissingNotamSource(NotamRepositoryPort):
    def active(self, at):
        raise NotamSourceUnavailable("directory not found")

    def all(self):
        raise NotamSourceUnavailable("directory not found")


@pytest.mark.parametrize("alt", [80, 500])
def test_a_misrouted_request_is_held_not_cleared(wired, graph, alt):
    """If the router sends a flight plan down the 'retrieve' route the validator
    never runs. Nothing was checked, so the flight must be held, whatever its
    altitude. (At 500m it would be a BLOCK if it had been validated.)"""
    container.override(llm=FixedRouteLLM(Action.RETRIEVE.value))
    decision = decide(plan(alt=alt), graph)
    assert decision.action is Action.RETRIEVE
    assert decision.verdict is Verdict.HOLD
    assert decision.requires_human
    assert decision.confidence == 0.0
    assert decision.ticket_id
    assert any("nothing cleared" in w for w in decision.warnings)


def test_the_act_route_is_held_even_when_no_other_warning_exists(wired, graph):
    """Holding an unchecked plan must not depend on the sample airspace happening
    to contain an unevaluable NOTAM. With only evaluable NOTAMs and no other
    warning, the plan is still held because nothing was retrieved to ground it."""
    container.override(notam_repository=InMemoryNotamRepository([CRANE, BIRDS]))
    decision = decide(plan(alt=80, query="D40 telemetry check"), graph)
    assert decision.action is Action.ACT
    assert decision.verdict is Verdict.HOLD
    assert decision.requires_human
    assert any("not cross-checked" in w for w in decision.warnings)


def test_an_unreadable_notam_source_holds_the_flight(wired, graph):
    container.override(notam_repository=MissingNotamSource())
    decision = decide(plan(alt=80), graph)
    assert decision.verdict is Verdict.HOLD
    assert decision.confidence == 0.0
    assert any("airspace not assessed" in w for w in decision.warnings)


CLAUSE_7 = "§7 Micro RPA ( <2kg ): Max altitude 120m AGL."


def test_the_rule_that_was_applied_is_fetched_by_name_not_left_to_similarity(wired, graph):
    """Similarity search returns something unrelated, as a real retriever sometimes
    will for a query that says nothing about §7. The validator applied CAR §7, so
    the retriever looks that rule up by identifier, and the citation is grounded."""
    store = RecordingVectorStore(["§12 Battery safety: swap if RUL <20 cycles."], defined=[CLAUSE_7])
    container.override(vector_store=store)
    decision = decide(plan(alt=80), graph)
    assert store.lookups == [["CAR §7"]]
    assert decision.retrieved[0] == CLAUSE_7, "defining chunks are listed first"
    assert [c.grounded for c in decision.citations] == [True]
    assert decision.verdict is Verdict.ALLOW


def test_a_store_that_cannot_look_a_rule_up_grounds_less_and_so_holds(wired, graph):
    """The port's default `lookup` returns nothing. That must fail closed."""
    container.override(vector_store=IrrelevantVectorStore())
    decision = decide(plan(alt=80), graph)
    assert decision.verdict is Verdict.HOLD
    assert [c.grounded for c in decision.citations] == [False]


def test_a_lookup_failure_holds_the_flight(wired, graph):
    class LookupDown(RecordingVectorStore):
        def lookup(self, refs):
            raise RetrievalUnavailable("lookup failed")

    container.override(vector_store=LookupDown([CLAUSE_7]))
    decision = decide(plan(alt=80), graph)
    assert decision.verdict is Verdict.HOLD
    assert decision.confidence == 0.0


def test_the_graph_runs_the_validator_before_the_retriever_on_the_both_route(wired, graph):
    order = []

    class Spy(RecordingVectorStore):
        def search(self, query, k=3):
            order.append("retriever")
            return super().search(query, k)

    class SpyNotams(InMemoryNotamRepository):
        def active(self, at):
            order.append("validator")
            return super().active(at)

    container.override(vector_store=Spy([CLAUSE_7], defined=[CLAUSE_7]),
                       notam_repository=SpyNotams([CRANE, BIRDS]))
    decide(plan(alt=80), graph)
    assert order == ["validator", "retriever"]
