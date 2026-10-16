"""Tripwire for the sample corpus in data/.

A NOTAM has a validity window, so sample data that is "in force" today quietly
stops being in force later. When that happened the demo silently changed from
BLOCK to ALLOW while the README and the tests still described the old behaviour.
This test fails *before* that happens, with a message that says what to do.
"""
from datetime import datetime, timedelta, timezone

from src.adapters.notam_repository import FileNotamRepository

#: Warn this long before a sample window closes.
MARGIN = timedelta(days=60)


def test_the_sample_notams_stay_in_force_for_the_demo():
    notams = {n.notam_id: n for n in FileNotamRepository().all()}
    horizon = datetime.now(timezone.utc) + MARGIN
    for notam_id in ("NOTAM 09/03", "NOTAM 09/04"):
        notam = notams[notam_id]
        assert notam.valid_to is not None
        assert notam.valid_to >= horizon, (
            f"{notam_id} stops being in force on {notam.valid_to:%Y-%m-%d}. Extend its "
            f"window in data/notams/ (the eval instant in src/eval.py must stay inside it), "
            f"or the demo will start returning different verdicts from the documentation.")


def test_the_golden_set_instant_is_inside_every_sample_window():
    """The eval pins time so results do not drift. That only works if the pinned
    instant is inside the windows the golden set was written against."""
    from src.eval import EVAL_INSTANT
    notams = {n.notam_id: n for n in FileNotamRepository().all()}
    for notam_id in ("NOTAM 09/03", "NOTAM 09/04"):
        assert notams[notam_id].is_active(EVAL_INSTANT)
