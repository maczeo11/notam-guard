from abc import ABC, abstractmethod
from typing import List

class VectorStorePort(ABC):
    @abstractmethod
    def search(self, query: str, k: int = 3) -> List[str]: ...

class MemoryPort(ABC):
    @abstractmethod
    def push(self, drone_id: str, ticket_id: str) -> List[str]: ...
    @abstractmethod
    def get(self, drone_id: str) -> List[str]: ...

class TicketPort(ABC):
    @abstractmethod
    def create(self, issue: str, severity: str, drone_id: str, notam_id: str = None) -> dict: ...

class LLMPort(ABC):
    @abstractmethod
    def route(self, query: str, has_coords: bool) -> str: ...
    @abstractmethod
    def respond(self, verdict: str, reason: str, citations: list) -> str: ...
