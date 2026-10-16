"""DynamoDB-backed approval tickets.

One table, partition key `pk` (string). The two kinds of item reuse the Redis key
names: `ticket:dedupe:<hash>` points at a ticket id, and `ticket:<id>` holds the ticket.

Expiry uses the table's TTL attribute `expires_at` (epoch seconds). DynamoDB deletes
expired items lazily, up to a couple of days late, so every read and every condition
here checks `expires_at` itself instead of trusting TTL to have run.

The guarantees come from conditional writes, which DynamoDB evaluates atomically on
the item: creating a ticket is one transaction that takes the dedupe key and writes the
ticket together, and approving is one update that only applies while the ticket is not
yet approved, so the first approver stands.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Optional
import logging
import time

from botocore.exceptions import BotoCoreError, ClientError

from src.adapters.ticket_adapter import _new_ticket_id, dedupe_key
from src.core.config import get_settings
from src.core.domain import Ticket
from src.core.errors import TicketStoreUnavailable
from src.core.ports import TicketPort

log = logging.getLogger(__name__)

_ATTEMPTS = 3


@contextmanager
def _store_errors(action: str):
    """Turn any AWS failure (throttling, no credentials, timeout) into one typed error."""
    try:
        yield
    except (ClientError, BotoCoreError) as exc:
        log.error("dynamodb %s failed: %s", action, exc)
        raise TicketStoreUnavailable(f"{action}: {exc}") from exc


def _cancellation_codes(exc: ClientError) -> list:
    return [reason.get("Code") for reason in exc.response.get("CancellationReasons", [])]


class DynamoTicketAdapter(TicketPort):
    """`resource` is a boto3 DynamoDB resource. `clock` is injectable so expiry can be tested."""

    def __init__(self, resource, table: str, clock: Callable[[], float] = time.time):
        self._table_name = table
        self._table = resource.Table(table)
        self._client = resource.meta.client       # takes plain Python values, like the resource
        self._clock = clock
        self._ttl = get_settings().ticket_ttl_seconds

    # -- reads ---------------------------------------------------------------------

    def _live_item(self, pk: str, now: int) -> Optional[dict]:
        """The item, or None if it is absent or past its expiry (even if not yet reaped)."""
        item = self._table.get_item(Key={"pk": pk}, ConsistentRead=True).get("Item")
        if item is None or int(item["expires_at"]) <= now:
            return None
        return item

    def _ticket(self, item: dict) -> Ticket:
        return Ticket(ticket_id=item["ticket_id"], key="", deduped=False,
                      ttl_seconds=self._ttl, issue=item.get("issue", ""),
                      severity=item.get("severity", "HIGH"),
                      status=item.get("status", "open"),
                      approved_by=item.get("approved_by", ""))

    def get(self, ticket_id: str) -> Optional[Ticket]:
        with _store_errors("get"):
            item = self._live_item(f"ticket:{ticket_id}", int(self._clock()))
        return self._ticket(item) if item else None

    # -- create --------------------------------------------------------------------

    def create(self, issue: str, severity: str, drone_id: str,
               notam_id: Optional[str] = None, at: Optional[datetime] = None) -> Ticket:
        at = at or datetime.now(timezone.utc)
        key = dedupe_key(drone_id, notam_id, issue, at)
        with _store_errors("create"):
            for _ in range(_ATTEMPTS):
                now = int(self._clock())
                # Reads are cheaper than a failed conditional write, so repeats take this path.
                existing = self._live_item(key, now)
                if existing:
                    return Ticket(ticket_id=existing["ticket_id"], key=key, deduped=True,
                                  ttl_seconds=self._ttl, issue=issue, severity=severity)
                ticket_id = _new_ticket_id()
                expires_at = now + self._ttl
                try:
                    self._client.transact_write_items(TransactItems=[
                        {"Put": {
                            "TableName": self._table_name,
                            "Item": {"pk": key, "ticket_id": ticket_id, "expires_at": expires_at},
                            "ConditionExpression": "attribute_not_exists(pk) OR expires_at <= :now",
                            "ExpressionAttributeValues": {":now": now}}},
                        {"Put": {
                            "TableName": self._table_name,
                            "Item": {"pk": f"ticket:{ticket_id}", "ticket_id": ticket_id,
                                     "issue": issue, "severity": severity, "drone_id": drone_id,
                                     "notam_id": notam_id or "", "status": "open",
                                     "created_at": at.isoformat(), "expires_at": expires_at},
                            # A 6-hex-digit id can collide; never overwrite someone else's ticket.
                            "ConditionExpression": "attribute_not_exists(pk) OR expires_at <= :now",
                            "ExpressionAttributeValues": {":now": now}}},
                    ])
                except ClientError as exc:
                    codes = _cancellation_codes(exc)
                    if exc.response["Error"]["Code"] == "TransactionCanceledException" and any(
                            code in ("ConditionalCheckFailed", "TransactionConflict")
                            for code in codes):
                        # Another caller took the dedupe key (read it next time round), or the
                        # id collided (draw a new one), or a competing transaction is mid-write.
                        continue
                    raise
                return Ticket(ticket_id=ticket_id, key=key, deduped=False, ttl_seconds=self._ttl,
                              issue=issue, severity=severity)
            raise TicketStoreUnavailable(
                f"could not settle a ticket for {key} after {_ATTEMPTS} attempts")

    # -- approve -------------------------------------------------------------------

    def approve(self, ticket_id: str, approver: str) -> Optional[Ticket]:
        """Close the gate. The first approval stands.

        The update applies only while the ticket exists, has not expired and is not
        already approved. If the condition fails, the ticket is read back: absent means
        unknown, otherwise it was already approved and is returned unchanged. `expires_at`
        is never written, so approving cannot make a ticket permanent.
        """
        key = f"ticket:{ticket_id}"
        with _store_errors("approve"):
            now = int(self._clock())
            try:
                result = self._table.update_item(
                    Key={"pk": key},
                    UpdateExpression="SET #s = :approved, approved_by = :who, approved_at = :at",
                    ConditionExpression="attribute_exists(pk) AND expires_at > :now AND #s <> :approved",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":approved": "approved", ":who": approver, ":now": now,
                        ":at": datetime.now(timezone.utc).isoformat()},
                    ReturnValues="ALL_NEW")
                return self._ticket(result["Attributes"])
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
            item = self._live_item(key, now)
        return self._ticket(item) if item else None


def connect() -> Optional[DynamoTicketAdapter]:
    """A ready adapter, or None if the table cannot be reached.

    Mirrors the Redis `connect`: a misconfigured demo should still run, with tickets
    kept in the process, rather than fail to start. The error is logged loudly.
    """
    settings = get_settings()
    try:
        import boto3
        from botocore.config import Config
        resource = boto3.resource("dynamodb", config=Config(
            region_name=settings.aws_region,
            retries={"max_attempts": 2, "mode": "standard"},
            connect_timeout=2, read_timeout=3))
        resource.Table(settings.dynamodb_table).load()      # one DescribeTable call
        return DynamoTicketAdapter(resource, settings.dynamodb_table)
    except Exception as exc:
        log.error("DynamoDB table %r unavailable (%s) — using in-process tickets",
                  settings.dynamodb_table, exc)
        return None
