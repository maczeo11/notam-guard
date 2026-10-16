"""The DynamoDB ticket store, exercised against moto's in-process DynamoDB.

moto does not run DynamoDB's TTL reaper, so an expired item stays in the table. That
is the situation the adapter has to handle on a real table too, because DynamoDB
deletes expired items lazily, up to a couple of days late. So the adapter checks
`expires_at` itself, and these tests move a fake clock past it.

moto's threads are not DynamoDB's servers, so the concurrency checks only run against a
real table: set DYNAMODB_TEST_TABLE (and AWS credentials) to run them.
"""
from concurrent.futures import ThreadPoolExecutor
import os
import uuid

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from src.adapters import dynamodb_ticket_adapter
from src.adapters.dynamodb_ticket_adapter import DynamoTicketAdapter
from src.adapters.ticket_adapter import InMemoryTicketAdapter
from src.app import app
from src.core import container
from src.core.config import reset_settings
from src.core.errors import TicketStoreUnavailable
from src.core.ports import TicketPort
from tests.conftest import NOW

TABLE = "notam-guard-tickets"
REGION = "ap-south-1"
DAY = 86400
LIVE_TABLE = os.getenv("DYNAMODB_TEST_TABLE")


class Clock:
    """A settable clock, so expiry can be tested without waiting a day."""

    def __init__(self, start: float = 1_800_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def aws(monkeypatch):
    for name, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                        "AWS_DEFAULT_REGION": REGION, "AWS_REGION": REGION}.items():
        monkeypatch.setenv(name, value)
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name=REGION)
        resource.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST")
        yield resource


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def tickets(aws, clock):
    return DynamoTicketAdapter(aws, TABLE, clock=clock)


def stored(aws) -> list:
    return aws.Table(TABLE).scan()["Items"]


def raw_expiry(aws, ticket_id: str) -> int:
    return int(aws.Table(TABLE).get_item(Key={"pk": f"ticket:{ticket_id}"})["Item"]["expires_at"])


def make(tickets, drone="D12", notam="NOTAM 09/03", issue="crane ceiling breached"):
    return tickets.create(issue, "HIGH", drone, notam, at=NOW)


def test_get_round_trips_a_ticket(tickets):
    created = make(tickets)
    fetched = tickets.get(created.ticket_id)
    assert (fetched.status, fetched.issue, fetched.severity) == ("open", "crane ceiling breached", "HIGH")
    assert created.deduped is False


def test_a_second_create_for_the_same_drone_and_notam_is_deduped(tickets, aws):
    first = make(tickets)
    again = make(tickets)
    assert again.deduped is True
    assert again.ticket_id == first.ticket_id
    assert len(stored(aws)) == 2, "one dedupe item and one ticket item, not two tickets"


def test_different_drones_get_different_tickets(tickets):
    assert make(tickets, drone="D12").ticket_id != make(tickets, drone="D40").ticket_id


def test_an_expired_dedupe_key_that_has_not_been_reaped_allows_a_new_ticket(tickets, aws, clock):
    first = make(tickets)
    clock.advance(DAY + 1)
    second = make(tickets)
    assert second.deduped is False
    assert second.ticket_id != first.ticket_id
    assert tickets.get(second.ticket_id) is not None


def test_an_expired_ticket_reads_as_absent_while_it_is_still_stored(tickets, aws, clock):
    ticket = make(tickets)
    clock.advance(DAY + 1)
    assert tickets.get(ticket.ticket_id) is None
    assert tickets.approve(ticket.ticket_id, "ops@example.com") is None
    assert any(item["pk"] == f"ticket:{ticket.ticket_id}" for item in stored(aws))


def test_approval_records_who_and_does_not_extend_the_expiry(tickets, aws):
    ticket = make(tickets)
    before = raw_expiry(aws, ticket.ticket_id)
    approved = tickets.approve(ticket.ticket_id, "ops@example.com")
    assert (approved.status, approved.approved_by) == ("approved", "ops@example.com")
    assert tickets.get(ticket.ticket_id).approved_by == "ops@example.com"
    assert raw_expiry(aws, ticket.ticket_id) == before, "approving must not make a ticket immortal"


def test_the_first_approval_stands(tickets):
    ticket = make(tickets)
    tickets.approve(ticket.ticket_id, "first@example.com")
    again = tickets.approve(ticket.ticket_id, "second@example.com")
    assert again.approved_by == "first@example.com"
    assert tickets.get(ticket.ticket_id).approved_by == "first@example.com"


def test_an_unknown_ticket_reads_and_approves_as_none(tickets):
    assert tickets.get("T-NOPE00") is None
    assert tickets.approve("T-NOPE00", "ops@example.com") is None


def test_a_ticket_id_collision_is_retried_and_never_overwrites(tickets, monkeypatch):
    ids = iter(["T-AAAAAA", "T-AAAAAA", "T-BBBBBB"])
    monkeypatch.setattr(dynamodb_ticket_adapter, "_new_ticket_id", lambda: next(ids))
    first = make(tickets, drone="D1", issue="first")
    second = make(tickets, drone="D2", issue="second")
    assert (first.ticket_id, second.ticket_id) == ("T-AAAAAA", "T-BBBBBB")
    assert tickets.get("T-AAAAAA").issue == "first"


@pytest.mark.parametrize("call", [
    lambda store: store.create("crane", "HIGH", "D12", "NOTAM 09/03", at=NOW),
    lambda store: store.get("T-ABC123"),
    lambda store: store.approve("T-ABC123", "ops@example.com"),
])
def test_an_unreachable_table_raises_a_typed_error(aws, clock, call):
    missing = DynamoTicketAdapter(aws, "no-such-table", clock=clock)
    with pytest.raises(TicketStoreUnavailable):
        call(missing)


def test_the_container_builds_the_dynamodb_store_when_configured(aws, monkeypatch):
    monkeypatch.setenv("TICKET_STORE", "dynamodb")
    monkeypatch.setenv("DYNAMODB_TABLE", TABLE)
    reset_settings()
    container.reset()
    assert isinstance(container.get_ticket_store(), DynamoTicketAdapter)


def test_the_container_falls_back_to_in_process_tickets_when_the_table_is_missing(aws, monkeypatch):
    monkeypatch.setenv("TICKET_STORE", "dynamodb")
    monkeypatch.setenv("DYNAMODB_TABLE", "no-such-table")
    reset_settings()
    container.reset()
    assert isinstance(container.get_ticket_store(), InMemoryTicketAdapter)


class DownStore(TicketPort):
    """A ticket store whose backend is unreachable."""

    def create(self, *args, **kwargs):
        raise TicketStoreUnavailable("down")

    def get(self, ticket_id):
        raise TicketStoreUnavailable("down")

    def approve(self, ticket_id, approver):
        raise TicketStoreUnavailable("down")


@pytest.fixture
def client_with_store_down(wired):
    container.override(ticket_store=DownStore())
    with TestClient(app) as test_client:
        yield test_client


def test_a_verdict_survives_the_ticket_store_being_down(client_with_store_down):
    body = client_with_store_down.post("/validate", json={
        "lat": 18.53, "lon": 73.84, "alt": 120, "drone_id": "D12",
        "query": "check crane NOTAM and DGCA CAR limits",
        "scheduled_for": NOW.isoformat()}).json()
    assert body["verdict"] == "BLOCK"
    assert body["requires_human"] is True
    assert body["ticket_id"] == ""
    assert any("ticket" in warning for warning in body["warnings"])


def test_approving_while_the_ticket_store_is_down_returns_503(client_with_store_down):
    response = client_with_store_down.post("/approve/T-ABC123", json={"approver": "ops@example.com"})
    assert response.status_code == 503


# --- against a real table -------------------------------------------------------------

live = pytest.mark.skipif(not LIVE_TABLE, reason="set DYNAMODB_TEST_TABLE to run against a real table")


def _real_adapter():
    # One session per thread: boto3 resources are not thread-safe.
    return DynamoTicketAdapter(boto3.session.Session().resource("dynamodb"), LIVE_TABLE)


def _cleanup(keys):
    table = boto3.resource("dynamodb").Table(LIVE_TABLE)
    for key in keys:
        table.delete_item(Key={"pk": key})


@live
def test_fifty_concurrent_creates_on_a_real_table_yield_one_ticket():
    drone = f"TEST-{uuid.uuid4().hex[:8]}"

    def create(_):
        return _real_adapter().create("crane ceiling breached", "HIGH", drone, "NOTAM 09/03")

    with ThreadPoolExecutor(max_workers=50) as pool:
        tickets = list(pool.map(create, range(50)))
    created = [t for t in tickets if not t.deduped]
    try:
        assert len(created) == 1
        assert {t.ticket_id for t in tickets} == {created[0].ticket_id}
    finally:
        _cleanup([created[0].key, f"ticket:{created[0].ticket_id}"] if created else [])


@live
def test_twenty_concurrent_approvals_on_a_real_table_leave_one_approver():
    drone = f"TEST-{uuid.uuid4().hex[:8]}"
    ticket = _real_adapter().create("crane ceiling breached", "HIGH", drone, "NOTAM 09/03")

    def approve(n):
        return _real_adapter().approve(ticket.ticket_id, f"user{n}")

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(approve, range(20)))
    try:
        winners = {r.approved_by for r in results}
        assert len(winners) == 1, f"callers saw different approvers: {winners}"
        assert _real_adapter().get(ticket.ticket_id).approved_by in winners
    finally:
        _cleanup([ticket.key, f"ticket:{ticket.ticket_id}"])
