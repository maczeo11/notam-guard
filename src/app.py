"""FastAPI surface for the compliance gate."""
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

from src.core import container  # noqa: E402
from src.core.config import get_settings  # noqa: E402
from src.core.domain import FlightPlan  # noqa: E402
from src.core.errors import TicketStoreUnavailable  # noqa: E402
from src.graph import decide, get_graph  # noqa: E402

log = logging.getLogger(__name__)


class FlightPlanRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: int = Field(..., ge=0, le=10000, description="Altitude AGL in metres")
    drone_id: str = Field(..., min_length=1, max_length=64)
    query: Optional[str] = Field(
        "validate flight against DGCA CAR and active NOTAMs", max_length=500,
        description="Free-text request. Capped so a public endpoint cannot be fed megabytes.")
    scheduled_for: Optional[datetime] = Field(
        None,
        description="When the flight will actually fly (UTC). NOTAMs are evaluated "
                    "against this instant, so a plan can be cleared ahead of time. "
                    "Defaults to now.")

    def to_domain(self) -> FlightPlan:
        return FlightPlan(lat=self.lat, lon=self.lon, alt=self.alt, drone_id=self.drone_id,
                          query=self.query or "", at=self.scheduled_for)


class EvidenceItem(BaseModel):
    ref: str
    grounded: bool
    excerpt: str


class ValidateResponse(BaseModel):
    verdict: str = Field(..., description="ALLOW | BLOCK | HOLD")
    reason: str
    confidence: float
    citations: List[str] = Field(default_factory=list,
                                 description="References the verdict relies on")
    evidence: List[EvidenceItem] = Field(default_factory=list,
                                         description="Each citation with the chunk supporting it")
    advisories: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list,
                                description="Airspace or evidence the system could not assess")
    requires_human: bool
    ticket_id: str = ""
    retrieved: List[str] = Field(default_factory=list)
    action: str = ""


class TicketResponse(BaseModel):
    ticket_id: str
    status: str
    severity: str = ""
    issue: str = ""
    approved_by: str = ""


class ApprovalRequest(BaseModel):
    approver: str = Field(..., min_length=1, max_length=64)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("NOTAM-Guard starting: vector=%s llm=%s tickets=%s tracing=%s",
             settings.vector_adapter, settings.llm_adapter, settings.ticket_store,
             settings.tracing_enabled)
    get_graph()  # compile once, not on the first request
    yield
    container.reset()


app = FastAPI(
    title="NOTAM-Guard",
    version="0.2.0",
    description="Agentic compliance gate for drone dispatch: DGCA CAR + NOTAM checks "
                "with grounded citations and a human-in-the-loop hold.",
    lifespan=lifespan,
)


@app.exception_handler(TicketStoreUnavailable)
def ticket_store_unavailable(_: Request, exc: TicketStoreUnavailable) -> JSONResponse:
    """A dead ticket store is a temporary refusal (503), not a server bug (500)."""
    log.error("ticket store unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "ticket store unavailable, try again"})


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": app.version}


@app.post("/validate", response_model=ValidateResponse)
def validate(request: FlightPlanRequest) -> ValidateResponse:
    decision = decide(request.to_domain())
    return ValidateResponse(
        verdict=decision.verdict.value,
        reason=decision.reason,
        confidence=decision.confidence,
        citations=[c.ref for c in decision.citations],
        evidence=[EvidenceItem(ref=c.ref, grounded=c.grounded, excerpt=c.excerpt)
                  for c in decision.citations],
        advisories=decision.advisories,
        warnings=decision.warnings,
        requires_human=decision.requires_human,
        ticket_id=decision.ticket_id,
        retrieved=decision.retrieved,
        action=decision.action.value,
    )


@app.get("/ticket/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: str) -> TicketResponse:
    ticket = container.get_ticket_store().get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"unknown ticket {ticket_id}")
    return TicketResponse(ticket_id=ticket.ticket_id, status=ticket.status,
                          severity=ticket.severity, issue=ticket.issue,
                          approved_by=ticket.approved_by)


@app.post("/approve/{ticket_id}", response_model=TicketResponse)
def approve_ticket(ticket_id: str, request: ApprovalRequest) -> TicketResponse:
    """Close the human-in-the-loop gate for a held or blocked flight. The first
    approval stands; approving an already-approved ticket returns it unchanged."""
    ticket = container.get_ticket_store().approve(ticket_id, request.approver)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"unknown ticket {ticket_id}")
    log.info("ticket %s approved by %s", ticket_id, ticket.approved_by)
    return TicketResponse(ticket_id=ticket.ticket_id, status=ticket.status,
                          severity=ticket.severity, issue=ticket.issue,
                          approved_by=ticket.approved_by)


@app.get("/notams")
def list_notams() -> dict:
    """The parsed corpus, including what the parser could not evaluate."""
    notams = container.get_notam_repository().all()
    return {
        "count": len(notams),
        "notams": [{
            "id": n.notam_id,
            "severity": n.severity.value,
            "geolocatable": n.is_geolocatable,
            "lat": n.lat,
            "lon": n.lon,
            "radius_km": n.radius_km,
            "max_alt_m": n.max_alt_m,
            "valid_from": n.valid_from.isoformat() if n.valid_from else None,
            "valid_to": n.valid_to.isoformat() if n.valid_to else None,
            "source": n.source,
        } for n in notams],
    }


@app.get("/drone/{drone_id}/history")
def drone_history(drone_id: str) -> dict:
    return {"drone_id": drone_id, "tickets": container.get_memory().get_history(drone_id)}
