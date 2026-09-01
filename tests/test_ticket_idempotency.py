"""Idempotent ticket creation under concurrency.

The README previously claimed a 50-concurrent 1/49 result that no test produced.
This is that test.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from src.adapters.ticket_adapter import InMemoryTicketAdapter, dedupe_key
from tests.conftest import NOW

CONCURRENCY = 50


def test_fifty_concurrent_creates_yield_exactly_one_ticket():
    store = InMemoryTicketAdapter()

    def create(_):
        return store.create("crane ceiling breached", "HIGH", "D12", "NOTAM 09/03", at=NOW)

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        tickets = list(pool.map(create, range(CONCURRENCY)))

    created = [t for t in tickets if not t.deduped]
    deduped = [t for t in tickets if t.deduped]
    assert len(created) == 1, "more than one ticket was opened for the same restriction"
    assert len(deduped) == CONCURRENCY - 1
    assert {t.ticket_id for t in deduped} == {created[0].ticket_id}


def test_different_drones_get_different_tickets():
    store = InMemoryTicketAdapter()
    first = store.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    second = store.create("crane", "HIGH", "D13", "NOTAM 09/03", at=NOW)
    assert not second.deduped
    assert first.ticket_id != second.ticket_id


def test_different_notams_get_different_tickets():
    store = InMemoryTicketAdapter()
    store.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    assert not store.create("runway", "HIGH", "D12", "NOTAM 09/04", at=NOW).deduped


def test_the_window_rolls_over_the_next_day():
    """A restriction that is still in force tomorrow deserves a fresh ticket."""
    store = InMemoryTicketAdapter()
    store.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    tomorrow = store.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW + timedelta(days=1))
    assert not tomorrow.deduped


def test_dedupe_key_is_stable_within_a_day_and_changes_across_days():
    same = dedupe_key("D12", "NOTAM 09/03", "crane", NOW)
    later_same_day = dedupe_key("D12", "NOTAM 09/03", "crane", NOW + timedelta(hours=6))
    next_day = dedupe_key("D12", "NOTAM 09/03", "crane", NOW + timedelta(days=1))
    assert same == later_same_day
    assert same != next_day


def test_approve_closes_the_gate():
    store = InMemoryTicketAdapter()
    ticket = store.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    assert store.approve(ticket.ticket_id, "ops@example.com").status == "approved"
    assert store.get(ticket.ticket_id).status == "approved"


def test_approving_an_unknown_ticket_returns_none():
    assert InMemoryTicketAdapter().approve("T-NOPE", "ops@example.com") is None
