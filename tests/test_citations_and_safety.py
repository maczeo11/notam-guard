"""Grounding and the safety policy.

The grounding check used to compare a hardcoded citation list against a
hardcoded retrieval list, so it could never fail. These tests exist to prove it
can now fail, and that failing holds the flight.
"""
import pytest

from src.core.citations import extract_refs, ground
from src.core.config import reset_settings
from src.core.domain import Citation, Verdict
from src.core.safety import finalise

CRANE_CHUNK = ("NOTAM 09/03 Pune Site: Crane 100m at 18.53,73.84 radius 1km. "
               "Max allowed 100m within radius. DGCA CAR §7 applies.")
CAR_CHUNK = "§7 Micro RPA ( <2kg ): Max altitude 120m AGL, UIN required."


def test_extract_refs_finds_both_reference_styles():
    refs = extract_refs(CRANE_CHUNK)
    assert "NOTAM 09/03" in refs
    assert "CAR §7" in refs


def test_extract_refs_deduplicates():
    assert extract_refs(f"{CRANE_CHUNK} {CRANE_CHUNK}").count("NOTAM 09/03") == 1


def test_citation_is_grounded_when_the_chunk_contains_it():
    citations = ground(["NOTAM 09/03"], [CRANE_CHUNK])
    assert citations[0].grounded
    assert "09/03" in citations[0].excerpt


def test_car_reference_matches_a_chunk_that_writes_it_differently():
    """The validator says 'CAR §7'; the corpus says '§7 Micro RPA'. Same rule."""
    assert ground(["CAR §7"], [CAR_CHUNK])[0].grounded


def test_citation_is_ungrounded_when_no_chunk_supports_it():
    citations = ground(["NOTAM 09/99"], [CRANE_CHUNK, CAR_CHUNK])
    assert citations[0].grounded is False
    assert citations[0].excerpt == ""


def test_clean_allow_is_auto_approved():
    outcome = finalise(violation=False, citations=[Citation("CAR §7", True)], warnings=[])
    assert outcome.verdict is Verdict.ALLOW
    assert outcome.requires_human is False
    assert outcome.confidence == 1.0


def test_allow_with_one_unevaluable_restriction_still_clears_but_is_less_confident():
    outcome = finalise(violation=False, citations=[Citation("CAR §7", True)],
                       warnings=["NOTAM 09/04 could not be evaluated geometrically"])
    assert outcome.verdict is Verdict.ALLOW
    assert outcome.confidence == 0.85


def test_ungrounded_citation_downgrades_an_allow_to_a_hold():
    """An ALLOW the system cannot show evidence for is not an ALLOW."""
    outcome = finalise(violation=False, citations=[Citation("NOTAM 09/99", False)], warnings=[])
    assert outcome.verdict is Verdict.HOLD
    assert outcome.requires_human is True
    assert any("not found in retrieved corpus" in w for w in outcome.warnings)


def test_retrieval_failure_holds_regardless_of_geometry():
    outcome = finalise(violation=False, citations=[], warnings=[], retrieval_failed=True)
    assert outcome.verdict is Verdict.HOLD
    assert outcome.confidence == 0.0
    assert outcome.requires_human is True


def test_block_always_reaches_a_human():
    outcome = finalise(violation=True, citations=[Citation("NOTAM 09/03", True)], warnings=[])
    assert outcome.verdict is Verdict.BLOCK
    assert outcome.requires_human is True


def test_a_chunk_that_only_mentions_a_rule_does_not_ground_it():
    """The crane NOTAM says 'DGCA CAR §7 applies'. That is a mention, not the
    clause, so it must not stand in for the text of §7."""
    assert ground(["CAR §7"], [CRANE_CHUNK])[0].grounded is False


def test_a_longer_clause_number_does_not_ground_a_shorter_one():
    assert ground(["CAR §7"], ["§70 Something else entirely."])[0].grounded is False
    assert ground(["NOTAM 09/03"], ["NOTAM 09/031 Another record."])[0].grounded is False


def test_a_clause_in_the_middle_of_a_chunk_grounds_and_the_excerpt_starts_there():
    chunk = "§8 Nano RPA ( <250g ): Max 50ft AGL. §7 Micro RPA ( <2kg ): Max altitude 120m AGL."
    citation = ground(["CAR §7"], [chunk])[0]
    assert citation.grounded
    assert citation.excerpt.startswith("§7 Micro RPA")


def test_a_leading_byte_order_mark_does_not_hide_a_reference():
    assert ground(["NOTAM 09/03"], ["﻿" + CRANE_CHUNK])[0].grounded


def test_a_plan_nothing_was_validated_for_is_held_outright():
    outcome = finalise(violation=False, citations=[], warnings=[], validated=False)
    assert outcome.verdict is Verdict.HOLD
    assert outcome.confidence == 0.0
    assert outcome.requires_human
    assert any("nothing cleared" in w for w in outcome.warnings)


def test_a_verdict_nothing_was_retrieved_for_is_held_and_priced():
    outcome = finalise(violation=False, citations=[], warnings=[], cross_checked=False)
    assert outcome.verdict is Verdict.HOLD
    assert outcome.requires_human
    assert outcome.confidence == pytest.approx(0.60)
    assert any("not cross-checked" in w for w in outcome.warnings)


def test_the_hold_for_an_unchecked_verdict_does_not_depend_on_the_gate_setting(monkeypatch):
    """A hold condition must hold even if someone lowers the confidence gate."""
    monkeypatch.setenv("HUMAN_GATE_CONFIDENCE", "0.10")
    reset_settings()
    outcome = finalise(violation=False, citations=[], warnings=[], cross_checked=False)
    assert outcome.verdict is Verdict.HOLD


def test_a_breach_is_still_a_block_when_nothing_was_retrieved():
    outcome = finalise(violation=True, citations=[], warnings=[], cross_checked=False)
    assert outcome.verdict is Verdict.BLOCK
    assert outcome.confidence == pytest.approx(0.55)


def test_the_unchecked_penalty_is_not_stacked_with_the_unevaluable_penalty():
    """One unevaluable NOTAM costs 0.15 and the missing cross-check costs 0.40.
    The cross-check warning itself must not be counted a second time as unevaluable."""
    outcome = finalise(violation=False, citations=[],
                       warnings=["NOTAM 09/04 could not be evaluated geometrically"],
                       cross_checked=False)
    assert outcome.confidence == pytest.approx(0.45)


def test_block_is_never_downgraded_by_weak_evidence():
    """Blocking is the safe direction, so poor evidence must not turn a BLOCK
    into an ALLOW — only into a lower-confidence BLOCK."""
    outcome = finalise(violation=True, citations=[Citation("NOTAM 09/99", False)],
                       warnings=["NOTAM 09/04 could not be evaluated geometrically"])
    assert outcome.verdict is Verdict.BLOCK
    assert outcome.confidence == pytest.approx(0.40)
