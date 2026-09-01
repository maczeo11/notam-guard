from dataclasses import dataclass
from typing import List

@dataclass
class FlightPlan:
    lat: float
    lon: float
    alt: int
    drone_id: str
    query: str = "validate flight DGCA NOTAM"

@dataclass
class Citation:
    id: str
    chunk: str

@dataclass
class Verdict:
    verdict: str  # ALLOW/BLOCK
    reason: str
    confidence: float
    citations: List[str]
    ticket_id: str = ""
    requires_human: bool = False
