"""Safety policy — the single place a verdict becomes final.

Two rules drive everything here:

1. The system fails closed. An ALLOW it cannot justify becomes a HOLD, never an
   ALLOW with a caveat. Retrieval failure, an ungrounded citation and an
   unevaluable restriction all push in the same direction.
2. Confidence is evidence quality, not a guess. It starts high for a
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

ALLOW_BASE_CONFIDENCE = 1.0
BLOCK_BASE_CONFIDENCE = 0.95


@dataclass
class SafetyOutcome:
    verdict: Verdict
    confidence: float
    requires_human: bool
    warnings: List[str]


def finalise(violation: bool,
             citations: Sequence[Citation],
             warnings: Sequence[str],
             retrieval_failed: bool = False) -> SafetyOutcome:
    """Turn a deterministic result plus its evidence into a final verdict."""
    settings = get_settings()
    warnings = list(warnings)

    if retrieval_failed:
        # We could not read the regulations. Nothing else about the flight matters.
        warnings.append("retrieval unavailable — flight held pending manual review")
        return SafetyOutcome(Verdict.HOLD, 0.0, True, warnings)

    ungrounded = [c.ref for c in citations if not c.grounded]
    if ungrounded:
        warnings.append(
            f"citation(s) not found in retrieved corpus: {', '.join(ungrounded)}")

    base = BLOCK_BASE_CONFIDENCE if violation else ALLOW_BASE_CONFIDENCE
    penalty = (UNEVALUABLE_PENALTY * len(warnings_unevaluable(warnings))
               + UNGROUNDED_PENALTY * len(ungrounded))
    confidence = max(0.0, round(base - penalty, 2))

    if violation:
        # Blocking is the safe direction, so a BLOCK is never downgraded — but it
        # always reaches a human, because refusing a mission has a cost too.
        return SafetyOutcome(Verdict.BLOCK, confidence, True, warnings)

    if confidence < settings.human_gate_confidence:
        return SafetyOutcome(Verdict.HOLD, confidence, True, warnings)

    return SafetyOutcome(Verdict.ALLOW, confidence, False, warnings)


def warnings_unevaluable(warnings: Sequence[str]) -> List[str]:
    """Warnings that represent airspace we could not assess, as opposed to the
    grounding warning, which is priced separately."""
    return [w for w in warnings if "not found in retrieved corpus" not in w]
