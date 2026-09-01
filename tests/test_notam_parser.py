from datetime import datetime, timezone

import pytest

from src.core.domain import Severity
from src.core.notam_parser import parse_many, parse_notam

CRANE = ("NOTAM 09/03 Pune Site: Crane 100m at 18.53,73.84 radius 1km "
         "valid 2026-09-01 to 2026-09-10. Max allowed 100m within radius. DGCA CAR §7 applies.")
RUNWAY = "NOTAM 09/04 Lohegaon Runway 10 closed 2026-09-02 to 2026-09-05 0600-1800 UTC. 5km no-fly."
BIRDS = "NOTAM 09/05 Bird activity reported 18.55,73.86 radius 2km dawn 0500-0800. Caution VFR."


def test_parses_a_fully_specified_notam():
    notam = parse_notam(CRANE, source="crane.txt")
    assert notam.notam_id == "NOTAM 09/03"
    assert (notam.lat, notam.lon) == (18.53, 73.84)
    assert notam.radius_km == 1.0
    assert notam.max_alt_m == 100
    assert notam.severity is Severity.RESTRICTIVE
    assert notam.is_geolocatable


def test_prefers_the_stated_limit_over_the_obstacle_height():
    """'Crane 100m' is the obstacle; 'Max allowed 100m' is the rule. Only the
    latter is a limit, so a NOTAM stating both must be read from the limit."""
    text = CRANE.replace("Max allowed 100m", "Max allowed 60m")
    assert parse_notam(text).max_alt_m == 60


def test_no_fly_zone_becomes_a_zero_ceiling():
    notam = parse_notam(RUNWAY)
    assert notam.max_alt_m == 0
    assert notam.radius_km == 5.0
    assert notam.severity is Severity.RESTRICTIVE


def test_notam_without_coordinates_is_not_geolocatable():
    """The runway NOTAM states a restriction but no position. It must survive
    parsing so the caller can report that it could not be evaluated."""
    notam = parse_notam(RUNWAY)
    assert notam.lat is None and notam.lon is None
    assert not notam.is_geolocatable


def test_caution_without_a_limit_is_advisory():
    notam = parse_notam(BIRDS)
    assert notam.severity is Severity.ADVISORY
    assert notam.max_alt_m is None


def test_validity_window_is_inclusive_of_the_final_day():
    notam = parse_notam(CRANE)
    assert notam.is_active(datetime(2026, 9, 10, 22, 0, tzinfo=timezone.utc))
    assert not notam.is_active(datetime(2026, 9, 11, 0, 30, tzinfo=timezone.utc))
    assert not notam.is_active(datetime(2026, 8, 31, 23, 0, tzinfo=timezone.utc))


def test_notam_without_a_window_is_treated_as_active():
    """Failing to parse dates must not silently retire a restriction."""
    notam = parse_notam(BIRDS)
    assert notam.valid_from is None
    assert notam.is_active(datetime(2030, 1, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize("text", ["", "not a notam at all", "09/03 without the keyword"])
def test_non_notam_text_returns_none(text):
    assert parse_notam(text) is None


def test_parse_many_reads_one_record_per_line():
    assert len(parse_many(f"{CRANE}\n\n{RUNWAY}\n{BIRDS}\n")) == 3
