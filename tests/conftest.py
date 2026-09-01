"""Shared fixtures.

Every test runs against injected adapters, so the suite needs no Postgres, no
Redis and no LLM provider.
"""
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.adapters.llm_adapter import RuleLLMAdapter  # noqa: E402
from src.adapters.notam_repository import InMemoryNotamRepository  # noqa: E402
from src.adapters.pgvector_adapter import InMemoryVectorAdapter  # noqa: E402
from src.adapters.redis_adapter import InMemoryMemoryAdapter  # noqa: E402
from src.adapters.ticket_adapter import InMemoryTicketAdapter  # noqa: E402
from src.core import container  # noqa: E402
from src.core.config import reset_settings  # noqa: E402
from src.core.domain import Notam, Severity  # noqa: E402

#: Inside NOTAM 09/03's validity window (2026-09-01 to 2026-09-10).
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)

CRANE = Notam(
    notam_id="NOTAM 09/03",
    text="NOTAM 09/03 Pune Site: Crane 100m at 18.53,73.84 radius 1km "
         "valid 2026-09-01 to 2026-09-10. Max allowed 100m within radius. DGCA CAR §7 applies.",
    source="notam_0903_crane.txt",
    lat=18.53, lon=73.84, radius_km=1.0, max_alt_m=100,
    valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
    valid_to=datetime(2026, 9, 10, 23, 59, 59, tzinfo=timezone.utc),
    severity=Severity.RESTRICTIVE,
)

BIRDS = Notam(
    notam_id="NOTAM 09/05",
    text="NOTAM 09/05 Bird activity reported 18.55,73.86 radius 2km dawn 0500-0800. Caution VFR.",
    source="notam_0905_bird.txt",
    lat=18.55, lon=73.86, radius_km=2.0, max_alt_m=None,
    severity=Severity.ADVISORY,
)

UNLOCATABLE = Notam(
    notam_id="NOTAM 09/04",
    text="NOTAM 09/04 Lohegaon Runway 10 closed 2026-09-02 to 2026-09-05 0600-1800 UTC. 5km no-fly.",
    source="notam_0904_runway.txt",
    lat=None, lon=None, radius_km=5.0, max_alt_m=0,
    valid_from=datetime(2026, 9, 2, tzinfo=timezone.utc),
    valid_to=datetime(2026, 9, 5, 23, 59, 59, tzinfo=timezone.utc),
    severity=Severity.RESTRICTIVE,
)

CORPUS = [
    "§7 Micro RPA ( <2kg ): Max altitude 120m AGL, UIN required, NPNT compliance mandatory.",
    "§9 All RPA must maintain 5km from airport, 1km from crane/obstacle as per NOTAM.",
    CRANE.text,
    BIRDS.text,
]


@pytest.fixture(autouse=True)
def clean_container(monkeypatch):
    """Reset cached settings and adapters around every test."""
    monkeypatch.setenv("VECTOR_ADAPTER", "memory")
    monkeypatch.setenv("LLM_ADAPTER", "rule")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    reset_settings()
    container.reset()
    yield
    container.reset()
    reset_settings()


@pytest.fixture
def notams():
    return [CRANE, UNLOCATABLE, BIRDS]


@pytest.fixture
def wired(notams):
    """Container wired to in-memory adapters over the standard fixture airspace."""
    container.override(
        vector_store=InMemoryVectorAdapter(CORPUS),
        notam_repository=InMemoryNotamRepository(notams),
        ticket_store=InMemoryTicketAdapter(),
        memory=InMemoryMemoryAdapter(),
        llm=RuleLLMAdapter(),
    )
    return container
