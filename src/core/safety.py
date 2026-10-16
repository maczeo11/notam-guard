"""Safety policy — the single place a verdict becomes final.

Three rules drive everything here:

1. The system fails closed. An ALLOW it cannot justify becomes a HOLD, never an
   ALLOW with a caveat. Retrieval failure, an ungrounded citation and an
   unevaluable restriction all push in the same direction.
2. A check that did not happen is a hold condition, not a deduction. If no flight
   plan was validated, or nothing was retrieved to ground the verdict, the flight
   is held outright. This does not depend on the confidence arithmetic landing
   below the gate, so changing a penalty or the gate cannot reopen it.
3. Confidence is evidence quality, not a guess. It starts high for a
   deterministic geometric result and is reduced by named, countable defects, so
   any number the API returns can be explained from the response itself.
"""
from dataclasses import dataclass
from typing import List, Sequence

from .config import get_settings
from .domain import Citation, Verdict

#: A restriction the parser could not evaluate (no coordinates, no radius).
UNEVALUABLE_PENALTY = 0.15
#: A reference the verdict rests on that appears in no retrieved chunk.
UNGROUNDED_PENALTY = 0.40
#: Nothing was retrieved, so no reference the verdict rests on could be checked.
UNCHECKED_PENALTY = 0.40

ALLOW_BASE_CONFIDENCE = 1.0
BLOCK_BASE_CONFIDENCE = 0.95

NOT_VALIDATED_WARNING = "no flight plan was validated on this route — nothing cleared"
NOT_CROSS_CHECKED_WARNING = ("verdict not cross-checked against the retrieved corpus "
                             "— nothing was retrieved to ground it")
_GROUNDING_PHRASE = "not found in retrieved corpus"


@dataclass
class SafetyOutcome:
    verdict: Verdict
    confidence: float
    requires_human: bool
    warnings: List[str]


def finalise(violation: bool,
             citations: Sequence[Citation],
             warnings: Sequence[str],
             retrieval_failed: bool = False,
             validated: bool = True,
             cross_checked: bool = True) -> SafetyOutcome:
    """Turn a deterministic result plus its evidence into a final verdict.

    `validated` is False when the deterministic validator did not produce a
    result (it was skipped by routing, or the NOTAM source was unreadable).
    `cross_checked` is False when nothing was retrieved to ground the verdict.
    """
    settings = get_settings()
    warnings = list(warnings)

    if retrieval_failed:
        # We could not read the regulations. Nothing else about the flight matters.
        warnings.append("retrieval unavailable — flight held pending manual review")
        return SafetyOutcome(Verdict.HOLD, 0.0, True, warnings)

    if not validated:
        # No deterministic result exists, so there is nothing to clear or to block.
        warnings.append(NOT_VALIDATED_WARNING)
        return SafetyOutcome(Verdict.HOLD, 0.0, True, warnings)

    ungrounded = [c.ref for c in citations if not c.grounded]
    if ungrounded:
        warnings.append(
            f"citation(s) {_GROUNDING_PHRASE}: {', '.join(ungrounded)}")

    # Counted before the cross-check warning is added, so that warning is priced
    # once, as UNCHECKED_PENALTY, and not a second time as an unevaluable restriction.
    unevaluable = len(warnings_unevaluable(warnings))
    unchecked = not cross_checked
    if unchecked:
        warnings.append(NOT_CROSS_CHECKED_WARNING)

    base = BLOCK_BASE_CONFIDENCE if violation else ALLOW_BASE_CONFIDENCE
    penalty = (UNEVALUABLE_PENALTY * unevaluable
               + UNGROUNDED_PENALTY * len(ungrounded)
               + (UNCHECKED_PENALTY if unchecked else 0.0))
    confidence = max(0.0, round(base - penalty, 2))

    if violation:
        # Blocking is the safe direction, so a BLOCK is never downgraded — but it
        # always reaches a human, because refusing a mission has a cost too.
        return SafetyOutcome(Verdict.BLOCK, confidence, True, warnings)

    if unchecked or confidence < settings.human_gate_confidence:
        return SafetyOutcome(Verdict.HOLD, confidence, True, warnings)

    return SafetyOutcome(Verdict.ALLOW, confidence, False, warnings)


def warnings_unevaluable(warnings: Sequence[str]) -> List[str]:
    """Warnings that represent airspace we could not assess, as opposed to the
    grounding warning, which is priced separately."""
    return [w for w in warnings if _GROUNDING_PHRASE not in w]
