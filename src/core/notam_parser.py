"""Parser for NOTAM free-text.

Real NOTAM text is not a schema. Some entries carry coordinates, a radius and an
altitude limit; others carry none of them. The parser extracts what is present
and records what is missing, because an unparsed restriction is a safety problem
that has to reach a human rather than be silently dropped.
"""
from datetime import datetime, time, timezone
from typing import List, Optional
import re

from .domain import Notam, Severity

_ID = re.compile(r"NOTAM\s+(\d{2}/\d{2})", re.I)
_COORDS = re.compile(r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)")
_RADIUS = re.compile(r"radius\s+(\d+(?:\.\d+)?)\s*km", re.I)
_NO_FLY = re.compile(r"(\d+(?:\.\d+)?)\s*km\s+no[- ]fly", re.I)
_MAX_ALT = re.compile(r"max(?:imum)?\s+(?:allowed\s+)?(\d+)\s*m\b", re.I)
_OBSTACLE_ALT = re.compile(r"(?:crane|tower|mast|obstacle)\s+(\d+)\s*m\b", re.I)
_WINDOW = re.compile(r"(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})")
_ADVISORY = re.compile(r"\b(caution|advisory|advised|reported)\b", re.I)


def _day_start(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _day_end(value: str) -> datetime:
    return datetime.combine(
        datetime.strptime(value, "%Y-%m-%d").date(), time.max, tzinfo=timezone.utc)


def parse_notam(text: str, source: str = "") -> Optional[Notam]:
    """Parse one NOTAM record. Returns None if no NOTAM id is present."""
    text = " ".join(text.split())
    match = _ID.search(text)
    if not match:
        return None
    notam_id = f"NOTAM {match.group(1)}"

    lat = lon = None
    if coords := _COORDS.search(text):
        lat, lon = float(coords.group(1)), float(coords.group(2))

    radius_km = None
    no_fly = _NO_FLY.search(text)
    if radius := _RADIUS.search(text):
        radius_km = float(radius.group(1))
    elif no_fly:
        radius_km = float(no_fly.group(1))

    # A no-fly zone is an altitude ceiling of zero; otherwise prefer an explicit
    # "max allowed" over an obstacle's own height, which is only a proxy for it.
    if no_fly:
        max_alt_m: Optional[int] = 0
    elif max_alt := _MAX_ALT.search(text):
        max_alt_m = int(max_alt.group(1))
    elif obstacle := _OBSTACLE_ALT.search(text):
        max_alt_m = int(obstacle.group(1))
    else:
        max_alt_m = None

    valid_from = valid_to = None
    if window := _WINDOW.search(text):
        valid_from = _day_start(window.group(1))
        valid_to = _day_end(window.group(2))

    # Only a NOTAM that states a hard limit can block. Anything else is surfaced
    # to the operator as an advisory rather than acted on automatically.
    restrictive = max_alt_m is not None
    if restrictive and _ADVISORY.search(text) and not no_fly and not _MAX_ALT.search(text):
        restrictive = False

    return Notam(
        notam_id=notam_id,
        text=text,
        source=source,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        max_alt_m=max_alt_m,
        valid_from=valid_from,
        valid_to=valid_to,
        severity=Severity.RESTRICTIVE if restrictive else Severity.ADVISORY,
    )


def parse_many(text: str, source: str = "") -> List[Notam]:
    """Parse a file that may hold several NOTAM records, one per line."""
    out = []
    for line in text.splitlines():
        if notam := parse_notam(line, source):
            out.append(notam)
    return out
