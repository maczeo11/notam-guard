"""Deterministic airspace checks.

Nothing in this module calls an LLM. The verdict for a flight plan is produced
here, by arithmetic over parsed NOTAMs, so that a language model can never be the
reason a flight was cleared.
"""
from typing import List, Optional
import logging
import math

from src.core.config import get_settings
from src.core.domain import FlightPlan, Notam, Severity, ValidationResult

log = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
DGCA_CEILING_REF = "CAR §7"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def notams_near(plan: FlightPlan, notams: List[Notam]) -> List[Notam]:
    """NOTAMs whose circle contains the flight position."""
    hits = []
    for notam in notams:
        if not notam.is_geolocatable:
            continue
        if haversine_km(plan.lat, plan.lon, notam.lat, notam.lon) <= notam.radius_km:
            hits.append(notam)
    return hits


def check_notam(lat: float, lon: float, notams: List[Notam], radius_km: float = 1.0) -> List[Notam]:
    """NOTAMs within `radius_km` of a point, regardless of altitude."""
    return [n for n in notams
            if n.is_geolocatable and haversine_km(lat, lon, n.lat, n.lon) <= radius_km]


def validate_flight(plan: FlightPlan, notams: List[Notam]) -> ValidationResult:
    """Evaluate one flight plan against the DGCA ceiling and the supplied NOTAMs.

    Returns a violation with the references it relied on, plus any advisories and
    any restriction the parser could not evaluate. Unevaluable restrictions are
    reported rather than ignored — the caller lowers confidence for each one.
    """
    settings = get_settings()
    advisories: List[str] = []
    warnings: List[str] = []

    for notam in notams:
        if notam.severity is Severity.RESTRICTIVE and not notam.is_geolocatable:
            warnings.append(
                f"{notam.notam_id} states a restriction but no usable coordinates/radius "
                f"— could not be evaluated geometrically")

    if plan.alt > settings.max_agl_m:
        return ValidationResult(
            violation=True,
            reason=(f"DGCA {DGCA_CEILING_REF}: micro RPA ceiling {settings.max_agl_m}m AGL "
                    f"breached at {plan.alt}m"),
            refs=[DGCA_CEILING_REF],
            advisories=advisories,
            warnings=warnings,
        )

    for notam in notams_near(plan, notams):
        distance = haversine_km(plan.lat, plan.lon, notam.lat, notam.lon)
        if notam.severity is Severity.ADVISORY:
            advisories.append(f"{notam.notam_id} within {distance:.2f}km: {notam.text}")
            continue
        if notam.max_alt_m is not None and plan.alt > notam.max_alt_m:
            ceiling = notam.max_alt_m
            suggestion = (f" — reduce to {max(ceiling - 20, 0)}m" if ceiling > 0
                          else " — area is no-fly, reroute required")
            return ValidationResult(
                violation=True,
                reason=(f"{notam.notam_id}: max {ceiling}m within {notam.radius_km}km, "
                        f"flight at {plan.alt}m and {distance:.2f}km away{suggestion}"),
                refs=[notam.notam_id],
                advisories=advisories,
                warnings=warnings,
                notam_id=notam.notam_id,
            )

    return ValidationResult(
        violation=False,
        reason=f"clear: {plan.alt}m within {settings.max_agl_m}m AGL and no restrictive NOTAM breached",
        refs=[DGCA_CEILING_REF],
        advisories=advisories,
        warnings=warnings,
    )
