"""The Redis adapters, exercised through a Redis-compatible server.

`test_ticket_idempotency.py` proves exactly-once for the in-process adapter, which
uses a lock. The production guarantee comes from `SET key value NX EX ttl` being
atomic on the server, so it needs its own proof. These tests use `fakeredis` with
one client per thread, which is the shape of several API processes sharing one
Redis. Set REDIS_TEST_URL to run the same checks against a real server.
"""
from concurrent.futures import ThreadPoolExecutor
import os

import fakeredis
import pytest
import redis

from src.adapters.redis_adapter import RedisMemoryAdapter, connect
from src.adapters.ticket_adapter import RedisTicketAdapter
from src.core.config import reset_settings
from tests.conftest import NOW

CONCURRENCY = 50
LIVE_URL = os.getenv("REDIS_TEST_URL")


@pytest.fixture
def server():
    return fakeredis.FakeServer()


def client_for(server):
    return fakeredis.FakeRedis(server=server)


def _concurrent_creates(make_adapter):
    def create(_):
        return make_adapter().create("crane ceiling breached", "HIGH", "D12",
                                     "NOTAM 09/03", at=NOW)

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        return list(pool.map(create, range(CONCURRENCY)))


def test_fifty_concurrent_creates_through_separate_clients_yield_one_ticket(server):
    tickets = _concurrent_creates(lambda: RedisTicketAdapter(client_for(server)))
    created = [t for t in tickets if not t.deduped]
    assert len(created) == 1
    assert {t.ticket_id for t in tickets if t.deduped} == {created[0].ticket_id}
    assert sum(t.deduped for t in tickets) == CONCURRENCY - 1


@pytest.mark.skipif(not LIVE_URL, reason="set REDIS_TEST_URL to run against a real Redis")
def test_fifty_concurrent_creates_against_a_real_redis_yield_one_ticket():
    probe = redis.from_url(LIVE_URL)
    probe.flushdb()
    tickets = _concurrent_creates(lambda: RedisTicketAdapter(redis.from_url(LIVE_URL)))
    assert sum(not t.deduped for t in tickets) == 1
    assert sum(t.deduped for t in tickets) == CONCURRENCY - 1


def test_a_ticket_and_its_dedupe_key_both_expire(server):
    client = client_for(server)
    ticket = RedisTicketAdapter(client).create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    assert 0 < client.ttl(f"ticket:{ticket.ticket_id}") <= 86400
    assert 0 < client.ttl(ticket.key) <= 86400


def test_get_round_trips_a_ticket(server):
    adapter = RedisTicketAdapter(client_for(server))
    created = adapter.create("crane ceiling", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    fetched = adapter.get(created.ticket_id)
    assert fetched.status == "open"
    assert fetched.issue == "crane ceiling"
    assert fetched.severity == "HIGH"


def test_approval_records_who_and_keeps_the_expiry(server):
    client = client_for(server)
    adapter = RedisTicketAdapter(client)
    ticket = adapter.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    approved = adapter.approve(ticket.ticket_id, "ops@example.com")
    assert approved.status == "approved"
    assert approved.approved_by == "ops@example.com"
    assert adapter.get(ticket.ticket_id).approved_by == "ops@example.com"
    assert client.ttl(f"ticket:{ticket.ticket_id}") > 0, "approving must not make a ticket immortal"


def test_the_first_approval_stands(server):
    adapter = RedisTicketAdapter(client_for(server))
    ticket = adapter.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)
    adapter.approve(ticket.ticket_id, "first@example.com")
    again = adapter.approve(ticket.ticket_id, "second@example.com")
    assert again.approved_by == "first@example.com"
    assert adapter.get(ticket.ticket_id).approved_by == "first@example.com"


def test_concurrent_approvals_leave_exactly_one_approver(server):
    adapter = RedisTicketAdapter(client_for(server))
    ticket = adapter.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW)

    def approve(n):
        return RedisTicketAdapter(client_for(server)).approve(ticket.ticket_id, f"user{n}")

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(approve, range(20)))
    winners = {r.approved_by for r in results}
    assert len(winners) == 1, f"callers saw different approvers: {winners}"
    assert adapter.get(ticket.ticket_id).approved_by in winners


def test_approving_an_unknown_ticket_returns_none(server):
    assert RedisTicketAdapter(client_for(server)).approve("T-NOPE", "ops@example.com") is None
    assert RedisTicketAdapter(client_for(server)).get("T-NOPE") is None


def test_history_keeps_the_five_most_recent_tickets_newest_first(server):
    memory = RedisMemoryAdapter(client_for(server))
    for n in range(7):
        history = memory.push_history("D12", f"T-{n}")
    assert history == ["T-6", "T-5", "T-4", "T-3", "T-2"]
    assert memory.get_history("D12") == history
    assert memory.get_history("D99") == []


def test_connect_returns_none_when_redis_is_unreachable(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    reset_settings()
    assert connect() is None
