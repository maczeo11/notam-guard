"""NOTAM sources. The file repository reads the corpus in `data/notams/`."""
from datetime import datetime
from pathlib import Path
from typing import List
import logging

from src.core.config import get_settings
from src.core.domain import Notam
from src.core.errors import NotamSourceUnavailable
from src.core.notam_parser import parse_many
from src.core.ports import NotamRepositoryPort

log = logging.getLogger(__name__)


class FileNotamRepository(NotamRepositoryPort):
    """Parses `*.txt` in the NOTAM directory. Cached after first read."""

    def __init__(self, directory: Path | None = None):
        self._directory = directory or get_settings().notam_dir
        self._cache: List[Notam] | None = None

    def all(self) -> List[Notam]:
        if self._cache is not None:
            return self._cache
        if not self._directory.is_dir():
            raise NotamSourceUnavailable(f"NOTAM directory not found: {self._directory}")
        notams: List[Notam] = []
        for path in sorted(self._directory.glob("*.txt")):
            try:
                notams.extend(parse_many(path.read_text(encoding="utf-8"), source=path.name))
            except OSError as exc:
                raise NotamSourceUnavailable(f"cannot read {path}: {exc}") from exc
        if not notams:
            raise NotamSourceUnavailable(f"no parsable NOTAMs in {self._directory}")
        log.info("loaded %d NOTAMs from %s", len(notams), self._directory)
        self._cache = notams
        return notams

    def active(self, at: datetime) -> List[Notam]:
        return [n for n in self.all() if n.is_active(at)]


class InMemoryNotamRepository(NotamRepositoryPort):
    """Test double — lets a test state the airspace explicitly."""

    def __init__(self, notams: List[Notam]):
        self._notams = list(notams)

    def all(self) -> List[Notam]:
        return list(self._notams)

    def active(self, at: datetime) -> List[Notam]:
        return [n for n in self._notams if n.is_active(at)]
