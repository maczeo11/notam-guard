"""API contract tests."""
import pytest
from fastapi.testclient import TestClient

from src.app import app
from tests.conftest import NOW


@pytest.fixture
def client(wired):
    with TestClient(app) as test_client:
        yield test_client


def post_plan(client, **overrides):
    # `scheduled_for` pins the NOTAM window, so results do not drift with the clock.
    body = {"lat": 18.53, "lon": 73.84, "alt": 120, "drone_id": "D12",
            "query": "check crane NOTAM and DGCA CAR limits",
            "scheduled_for": NOW.isoformat()}
    body.update(overrides)
    return client.post("/validate", json=body)


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_validate_returns_a_grounded_block(client):
    body = post_plan(client).json()
    assert body["verdict"] == "BLOCK"
    assert body["citations"] == ["NOTAM 09/03"]
    assert body["evidence"][0]["grounded"] is True
    assert body["evidence"][0]["excerpt"]
    assert body["requires_human"] is True
    assert body["ticket_id"]


def test_validate_returns_an_allow_without_a_ticket(client):
    body = post_plan(client, alt=80).json()
    assert body["verdict"] == "ALLOW"
    assert body["requires_human"] is False
    assert body["ticket_id"] == ""


def test_validate_reports_what_it_could_not_assess(client):
    assert any("09/04" in w for w in post_plan(client, alt=80).json()["warnings"])


def test_notam_window_is_evaluated_against_the_scheduled_time(client):
    """The same position and altitude that breaches the crane NOTAM today is
    clear once that NOTAM has expired on 2026-09-10."""
    assert post_plan(client).json()["verdict"] == "BLOCK"
    after_expiry = post_plan(client, scheduled_for="2026-09-15T12:00:00+00:00").json()
    assert after_expiry["verdict"] == "ALLOW"


@pytest.mark.parametrize("field,value", [
    ("lat", 91), ("lat", -91), ("lon", 181), ("alt", -1), ("drone_id", ""),
])
def test_validate_rejects_out_of_range_input(client, field, value):
    assert post_plan(client, **{field: value}).status_code == 422


def test_ticket_lifecycle_through_the_human_gate(client):
    ticket_id = post_plan(client).json()["ticket_id"]

    assert client.get(f"/ticket/{ticket_id}").json()["status"] == "open"

    approved = client.post(f"/approve/{ticket_id}", json={"approver": "ops@example.com"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client.get(f"/ticket/{ticket_id}").json()["status"] == "approved"


def test_unknown_ticket_is_404(client):
    assert client.get("/ticket/T-NOPE").status_code == 404
    assert client.post("/approve/T-NOPE", json={"approver": "ops"}).status_code == 404


def test_notams_endpoint_exposes_unevaluable_records(client):
    body = client.get("/notams").json()
    runway = next(n for n in body["notams"] if n["id"] == "NOTAM 09/04")
    assert runway["geolocatable"] is False


def test_drone_history_lists_tickets(client):
    ticket_id = post_plan(client).json()["ticket_id"]
    assert ticket_id in client.get("/drone/D12/history").json()["tickets"]
