"""Citation extraction and grounding.

A citation is only worth printing if the text it points at was actually
retrieved. "Retrieved" has to mean the rule itself, not a passing mention of it:
the crane NOTAM says "DGCA CAR §7 applies", and that sentence must not be able to
stand in for the text of §7.

So a reference is grounded only where it *defines* something: at the start of a
chunk, or at the start of a sentence inside one (`§8 ... . §7 ...`), and as a whole
number, so `§7` is not satisfied by `§70`.
"""
from typing import List, Optional, Sequence, Tuple
import re

from .domain import Citation

_NOTAM_REF = re.compile(r"NOTAM\s+(\d{2}/\d{2})", re.I)
_CAR_REF = re.compile(r"(?:CAR\s+)?§\s*(\d+)", re.I)

#: Where a definition may begin: the start of the chunk, or just after a sentence
#: boundary. Leading punctuation and a byte-order mark are skipped.
_AT_BOUNDARY = r"(?:^|[.;:]\s)\W*"


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


def needle(ref: str) -> str:
    """The distinctive part of a reference: 'CAR §7' → '§7', 'NOTAM 09/03' → '09/03'.

    A coarse key for narrowing a search, such as the SQL prefilter in
    `PgVectorAdapter.lookup`. It is not proof of anything: whether a chunk
    *defines* the reference is decided by `find_definition`.
    """
    if match := _NOTAM_REF.search(ref):
        return match.group(1)
    if match := _CAR_REF.search(ref):
        return f"§{match.group(1)}"
    return ref.lower()


def _definition(ref: str) -> re.Pattern:
    """A pattern whose group 'ref' is the reference, where it defines something."""
    if match := _NOTAM_REF.search(ref):
        return re.compile(
            rf"{_AT_BOUNDARY}(?P<ref>NOTAM\s+{re.escape(match.group(1))})(?![\d/])", re.I)
    if match := _CAR_REF.search(ref):
        return re.compile(rf"{_AT_BOUNDARY}(?P<ref>§\s*{match.group(1)})(?!\d)")
    # A reference style we have no structure for: plain containment.
    return re.compile(rf"(?P<ref>{re.escape(ref)})", re.I)


def find_definition(ref: str, chunk: str) -> Optional[int]:
    """Index in `chunk` where `ref` is defined, or None. The one rule for what
    counts as the text of a reference; grounding and lookup both use it."""
    match = _definition(ref).search(chunk)
    return match.start("ref") if match else None


def ground(refs: Sequence[str], retrieved: Sequence[str], excerpt_chars: int = 160) -> List[Citation]:
    """Match each reference against the retrieved chunks.

    Returns one Citation per reference; `grounded` is False when no retrieved
    chunk defines it, which is the caller's signal to hold the flight. The excerpt
    starts at the definition, so a chunk holding several clauses shows the right one.
    """
    citations = []
    for ref in refs:
        hit: Optional[Tuple[str, int]] = None
        for chunk in retrieved:
            start = find_definition(ref, chunk)
            if start is not None:
                hit = (chunk, start)
                break
        text = hit[0][hit[1]:hit[1] + excerpt_chars] if hit else ""
        citations.append(Citation(ref=ref, grounded=hit is not None, excerpt=text))
    return citations
