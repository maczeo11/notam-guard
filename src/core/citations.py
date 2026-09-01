"""Citation extraction and grounding.

A citation is only worth printing if the text it points at was actually
retrieved. Previously the citation list was a hardcoded constant, so the
grounding check compared two fixed values and could never fail.
"""
from typing import List, Sequence
import re

from .domain import Citation

_NOTAM_REF = re.compile(r"NOTAM\s+(\d{2}/\d{2})", re.I)
_CAR_REF = re.compile(r"(?:CAR\s+)?§\s*(\d+)", re.I)


def extract_refs(text: str) -> List[str]:
    """Every regulatory reference mentioned in a piece of text."""
    refs = [f"NOTAM {m.group(1)}" for m in _NOTAM_REF.finditer(text)]
    refs += [f"CAR §{m.group(1)}" for m in _CAR_REF.finditer(text)]
    seen, unique = set(), []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique.append(ref)
    return unique


def _needle(ref: str) -> str:
    """The distinctive part of a reference, so 'CAR §7' matches a chunk that
    writes it as '§7 Micro RPA' and 'NOTAM 09/03' matches '09/03'."""
    if match := _NOTAM_REF.search(ref):
        return match.group(1)
    if match := _CAR_REF.search(ref):
        return f"§{match.group(1)}"
    return ref.lower()


def ground(refs: Sequence[str], retrieved: Sequence[str], excerpt_chars: int = 160) -> List[Citation]:
    """Match each reference against the retrieved chunks.

    Returns one Citation per reference; `grounded` is False when no retrieved
    chunk contains it, which is the caller's signal to hold the flight.
    """
    citations = []
    for ref in refs:
        needle = _needle(ref).lower()
        support = next((c for c in retrieved if needle in c.lower()), None)
        citations.append(Citation(
            ref=ref,
            grounded=support is not None,
            excerpt=(support or "")[:excerpt_chars],
        ))
    return citations
