"""Boundary tests for the deterministic validator.

Every threshold in the system is exercised from both sides, because these
comparisons are the only thing standing between a flight plan and a clearance.
"""
from dataclasses import replace

import pytest

from src.core.domain import FlightPlan
from src.tools import haversine_km, notams_near, validate_flight
from tests.conftest import BIRDS, CRANE, NOW, UNLOCATABLE


def plan(lat=18.53, lon=73.84, alt=80, drone_id="D1"):
    return FlightPlan(lat=lat, lon=lon, alt=alt, drone_id=drone_id, at=NOW)


def test_haversine_matches_a_known_distance():
    # 0.01 degrees of latitude is ~1.11 km anywhere on the globe.
    assert haversine_km(18.53, 73.84, 18.54, 73.84) == pytest.approx(1.112, abs=0.01)
    assert haversine_km(18.53, 73.84, 18.53, 73.84) == 0.0


@pytest.mark.parametrize("alt,violation", [(119, False), (120, False), (121, True), (130, True)])
def test_dgca_ceiling_boundary(alt, violation, notams):
    """§7 is 'max 120m', so 120 is legal and 121 is not."""
    result = validate_flight(plan(lat=19.0, lon=74.0, alt=alt), notams)
    assert result.violation is violation
    if violation:
        assert result.refs == ["CAR §7"]


@pytest.mark.parametrize("alt,violation", [(99, False), (100, False), (101, True), (120, True)])
def test_crane_ceiling_boundary(alt, violation, notams):
    result = validate_flight(plan(alt=alt), notams)
    assert result.violation is violation
    if violation:
        assert result.refs == ["NOTAM 09/03"]
        assert "reduce to 80m" in result.reason


def test_dgca_ceiling_is_checked_before_notams(notams):
    """Above 120m the flight is illegal regardless of local NOTAMs, and the
    citation must say so rather than blaming the nearest crane."""
    result = validate_flight(plan(alt=130), notams)
    assert result.refs == ["CAR §7"]


def test_position_outside_the_notam_radius_is_clear(notams):
    # 18.52,73.85 is ~1.53km from the crane, outside its 1km radius.
    result = validate_flight(plan(lat=18.52, lon=73.85, alt=120), notams)
    assert result.violation is False


def test_position_just_inside_the_radius_is_blocked(notams):
    result = validate_flight(plan(lat=18.531, lon=73.841, alt=120), notams)
    assert result.violation is True
    assert result.notam_id == "NOTAM 09/03"


def test_advisory_notam_is_reported_but_never_blocks(notams):
    result = validate_flight(plan(lat=18.55, lon=73.86, alt=90), notams)
    assert result.violation is False
    assert any("09/05" in a for a in result.advisories)


def test_unevaluable_restriction_is_warned_about_not_ignored(notams):
    """NOTAM 09/04 declares a 5km no-fly but carries no coordinates. Dropping it
    silently would be the failure mode this warning exists to prevent."""
    result = validate_flight(plan(), notams)
    assert any("09/04" in w for w in result.warnings)


def test_no_fly_zone_suggests_a_reroute_not_a_lower_altitude():
    located_no_fly = replace(UNLOCATABLE, lat=18.53, lon=73.84, radius_km=5.0)
    result = validate_flight(plan(alt=50), [located_no_fly])
    assert result.violation is True
    assert "no-fly" in result.reason


def test_notams_near_ignores_records_without_a_position():
    assert UNLOCATABLE not in notams_near(plan(), [CRANE, UNLOCATABLE, BIRDS])
