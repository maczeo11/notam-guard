"""Domain types shared by the graph, the adapters and the API layer.

These are the vocabulary of the system: everything that crosses a port boundary
is one of these, so the ports stay independent of FastAPI, Redis and psycopg2.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    #: Emitted when the system cannot justify a decision — a failed retrieval, an
    #: ungrounded citation, an un-geolocatable NOTAM. Never auto-approved.
    HOLD = "HOLD"


class Action(str, Enum):
    RETRIEVE = "retrieve"
    ACT = "act"
    BOTH = "both"


class Severity(str, Enum):
    #: Hard constraint — breaching it is a violation.
    RESTRICTIVE = "restrictive"
    #: Informational — surfaced to the operator, never auto-blocks.
    ADVISORY = "advisory"


@dataclass(frozen=True)
class FlightPlan:
    lat: float
    lon: float
    alt: int
    drone_id: str
    query: str = "validate flight against DGCA CAR and active NOTAMs"
    at: Optional[datetime] = None

    def when(self) -> datetime:
        return self.at or datetime.now(timezone.utc)


@dataclass(frozen=True)
class Notam:
    """A parsed NOTAM. Fields are Optional because real NOTAM free-text is not
    guaranteed to carry coordinates or an altitude limit; see `is_geolocatable`."""
    notam_id: str
    text: str
    source: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius_km: Optional[float] = None
    max_alt_m: Optional[int] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    severity: Severity = Severity.RESTRICTIVE

    @property
    def is_geolocatable(self) -> bool:
        return self.lat is not None and self.lon is not None and self.radius_km is not None

    def is_active(self, at: datetime) -> bool:
        """A NOTAM with no stated window is treated as active — withholding a
        restriction because we failed to parse its dates would fail open."""
        if self.valid_from and at < self.valid_from:
            return False
        if self.valid_to and at > self.valid_to:
            return False
        return True


@dataclass(frozen=True)
class Citation:
    """A reference the verdict rests on, plus the retrieved text that supports it.

    `grounded` is False when the reference could not be found in any retrieved
    chunk — the signal that the system is asserting something it cannot show.
    """
    ref: str
    grounded: bool
    excerpt: str = ""


@dataclass
class ValidationResult:
    """Output of the deterministic validator. Contains no LLM-produced text."""
    violation: bool
    reason: str
    refs: List[str] = field(default_factory=list)
    advisories: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notam_id: Optional[str] = None


@dataclass
class Ticket:
    ticket_id: str
    key: str
    deduped: bool
    ttl_seconds: int
    issue: str = ""
    severity: str = "HIGH"
    status: str = "open"


@dataclass
class Decision:
    """The finalised answer for one flight plan."""
    verdict: Verdict
    reason: str
    confidence: float
    citations: List[Citation] = field(default_factory=list)
    retrieved: List[str] = field(default_factory=list)
    advisories: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    requires_human: bool = False
    ticket_id: str = ""
    action: Action = Action.BOTH
