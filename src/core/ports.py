"""Ports — the abstract boundary between the decision logic and infrastructure.

Every port here has at least two adapters (a real one and a test double) and is
resolved through `core.container`. Nothing in `graph.py` or `tools.py` imports a
concrete adapter directly.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from .domain import Notam, Ticket


class VectorStorePort(ABC):
    @abstractmethod
    def search(self, query: str, k: int = 3) -> List[str]:
        """Return up to `k` chunks most similar to `query`.

        Raises:
            RetrievalUnavailable: if the store cannot be queried. Implementations
                must raise rather than return a fallback — the caller decides the
                safe response, and the safe response is not a fabricated chunk.
        """


class MemoryPort(ABC):
    @abstractmethod
    def push_history(self, drone_id: str, ticket_id: str) -> List[str]:
        """Record a ticket against a drone and return its recent history."""

    @abstractmethod
    def get_history(self, drone_id: str) -> List[str]:
        ...

    @abstractmethod
    def add_tile(self, lat: float, lon: float, drone_id: str) -> str:
        """Remember that `drone_id` was cleared near this position. Returns the tile key."""

    @abstractmethod
    def get_tile(self, lat: float, lon: float) -> Optional[str]:
        ...


class TicketPort(ABC):
    @abstractmethod
    def create(self, issue: str, severity: str, drone_id: str,
               notam_id: Optional[str] = None, at: Optional[datetime] = None) -> Ticket:
        """Create a ticket idempotently.

        Concurrent calls with the same (drone, notam, window) must yield exactly
        one ticket; every other caller receives `deduped=True`.
        """

    @abstractmethod
    def get(self, ticket_id: str) -> Optional[Ticket]:
        ...

    @abstractmethod
    def approve(self, ticket_id: str, approver: str) -> Optional[Ticket]:
        """Close the human-in-the-loop gate for one held flight."""


class NotamRepositoryPort(ABC):
    @abstractmethod
    def active(self, at: datetime) -> List[Notam]:
        """NOTAMs in force at `at`."""

    @abstractmethod
    def all(self) -> List[Notam]:
        ...


class LLMPort(ABC):
    @abstractmethod
    def route(self, query: str, has_coords: bool) -> str:
        """Return one of 'retrieve' | 'act' | 'both'."""

    @abstractmethod
    def respond(self, verdict: str, reason: str, citations: List[str]) -> str:
        """Render an operator-facing sentence. Must not change the verdict."""
