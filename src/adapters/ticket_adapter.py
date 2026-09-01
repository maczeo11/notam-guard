"""Idempotent ticket creation.

The dedupe key is `hash(drone_id | notam_id | window)`. Two dispatchers reacting
to the same restriction in the same 24h window must produce one ticket, not two,
so the atomic primitive (`SET NX`) is what makes the ticket correct — not a
best-effort check-then-write.
"""
from datetime import datetime, timezone
from typing import Optional
import hashlib
import json
import logging
import threading
import uuid

from src.core.config import get_settings
from src.core.domain import Ticket
from src.core.ports import TicketPort

log = logging.getLogger(__name__)


def dedupe_key(drone_id: str, notam_id: Optional[str], issue: str, at: datetime) -> str:
    """Stable key for one (drone, restriction, day) triple."""
    window = at.strftime("%Y-%m-%d")
    raw = f"{drone_id}|{notam_id or issue[:30]}|{window}"
    return f"ticket:dedupe:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _new_ticket_id() -> str:
    return f"T-{uuid.uuid4().hex[:6].upper()}"


class RedisTicketAdapter(TicketPort):
    """Real idempotency via `SET key val NX EX ttl`."""

    def __init__(self, client):
        self._r = client
        self._ttl = get_settings().ticket_ttl_seconds

    def create(self, issue: str, severity: str, drone_id: str,
               notam_id: Optional[str] = None, at: Optional[datetime] = None) -> Ticket:
        at = at or datetime.now(timezone.utc)
        key = dedupe_key(drone_id, notam_id, issue, at)
        ticket_id = _new_ticket_id()

        # The single atomic step: exactly one caller sees True.
        won = self._r.set(key, ticket_id, nx=True, ex=self._ttl)
        if not won:
            existing = self._r.get(key)
            existing = existing.decode() if isinstance(existing, bytes) else existing
            return Ticket(ticket_id=existing or "", key=key, deduped=True, ttl_seconds=self._ttl,
                          issue=issue, severity=severity)

        record = {"ticket_id": ticket_id, "issue": issue, "severity": severity,
                  "drone_id": drone_id, "notam_id": notam_id or "", "status": "open",
                  "created_at": at.isoformat()}
        self._r.set(f"ticket:{ticket_id}", json.dumps(record), ex=self._ttl)
        return Ticket(ticket_id=ticket_id, key=key, deduped=False, ttl_seconds=self._ttl,
                      issue=issue, severity=severity)

    def get(self, ticket_id: str) -> Optional[Ticket]:
        raw = self._r.get(f"ticket:{ticket_id}")
        if not raw:
            return None
        record = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return Ticket(ticket_id=record["ticket_id"], key="", deduped=False,
                      ttl_seconds=self._ttl, issue=record.get("issue", ""),
                      severity=record.get("severity", "HIGH"),
                      status=record.get("status", "open"))

    def approve(self, ticket_id: str, approver: str) -> Optional[Ticket]:
        raw = self._r.get(f"ticket:{ticket_id}")
        if not raw:
            return None
        record = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        record["status"] = "approved"
        record["approved_by"] = approver
        record["approved_at"] = datetime.now(timezone.utc).isoformat()
        self._r.set(f"ticket:{ticket_id}", json.dumps(record), ex=self._ttl)
        return Ticket(ticket_id=ticket_id, key="", deduped=False, ttl_seconds=self._ttl,
                      issue=record.get("issue", ""), severity=record.get("severity", "HIGH"),
                      status="approved")


class InMemoryTicketAdapter(TicketPort):
    """Process-local fallback. A lock gives the same exactly-once guarantee that
    `SET NX` gives across processes, so the dedupe tests pass without Redis."""

    def __init__(self):
        self._lock = threading.Lock()
        self._keys: dict[str, tuple[float, str]] = {}
        self._tickets: dict[str, Ticket] = {}
        self._ttl = get_settings().ticket_ttl_seconds

    def create(self, issue: str, severity: str, drone_id: str,
               notam_id: Optional[str] = None, at: Optional[datetime] = None) -> Ticket:
        at = at or datetime.now(timezone.utc)
        key = dedupe_key(drone_id, notam_id, issue, at)
        now = at.timestamp()
        with self._lock:
            if key in self._keys:
                created, existing_id = self._keys[key]
                if now - created < self._ttl:
                    return Ticket(ticket_id=existing_id, key=key, deduped=True,
                                  ttl_seconds=self._ttl, issue=issue, severity=severity)
            ticket_id = _new_ticket_id()
            self._keys[key] = (now, ticket_id)
            ticket = Ticket(ticket_id=ticket_id, key=key, deduped=False, ttl_seconds=self._ttl,
                            issue=issue, severity=severity)
            self._tickets[ticket_id] = ticket
            return ticket

    def get(self, ticket_id: str) -> Optional[Ticket]:
        with self._lock:
            return self._tickets.get(ticket_id)

    def approve(self, ticket_id: str, approver: str) -> Optional[Ticket]:
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                return None
            ticket.status = "approved"
            return ticket
