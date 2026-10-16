"""Evaluation harness.

Reports routing, verdict, retrieval and grounding as four separate numbers.
They are separate on purpose: the verdict comes from deterministic geometry, so
scoring it together with retrieval would let a perfect arithmetic score hide a
retriever that returns nothing useful.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List
import argparse
import json
import logging
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import container  # noqa: E402
from src.core.citations import ground  # noqa: E402
from src.core.config import REPO_ROOT, get_settings  # noqa: E402
from src.core.domain import FlightPlan, Verdict  # noqa: E402
from src.core.errors import RetrievalUnavailable  # noqa: E402
from src.graph import decide  # noqa: E402

log = logging.getLogger(__name__)

# The golden set is scored at a fixed instant so results do not change with the wall
# clock. It must fall inside the windows of the sample NOTAMs in data/notams/
# (tests/test_sample_data.py checks that, and that the windows have not lapsed).
EVAL_INSTANT = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


@dataclass
class Row:
    id: str
    note: str
    action_ok: bool
    verdict_ok: bool
    retrieval_ok: bool | None
    grounded_ok: bool
    verdict: str
    expected_verdict: str
    confidence: float
    latency_ms: float
    warnings: List[str] = field(default_factory=list)


def evaluate(cases: List[dict]) -> List[Row]:
    import time
    rows = []
    for case in cases:
        plan = FlightPlan(lat=case["lat"], lon=case["lon"], alt=case["alt"],
                          drone_id=case["drone_id"], query=case["query"], at=EVAL_INSTANT)
        start = time.perf_counter()
        decision = decide(plan)
        elapsed = (time.perf_counter() - start) * 1000

        # retrieval_ok measures *similarity search on its own*: did the top-k for this
        # query include the chunk that defines the expected reference? The graph also
        # fetches cited rules by identifier (`lookup`), which would make this number
        # trivially 1.0 and hide a weak retriever, so it is deliberately not counted
        # here. It is scored with the same rule the safety gate uses: the reference
        # must be defined by the chunk, not merely mentioned in it.
        expected_citation = case.get("expected_citation")
        if expected_citation:
            try:
                top_k = container.get_vector_store().search(
                    case["query"], k=get_settings().retrieval_k)
            except RetrievalUnavailable:
                top_k = []
            retrieval_ok = ground([expected_citation], top_k)[0].grounded
        else:
            retrieval_ok = None

        rows.append(Row(
            id=case["id"],
            note=case.get("note", ""),
            action_ok=decision.action.value == case.get("expected_action", decision.action.value),
            verdict_ok=decision.verdict.value == case["expected_verdict"],
            retrieval_ok=retrieval_ok,
            grounded_ok=all(c.grounded for c in decision.citations),
            verdict=decision.verdict.value,
            expected_verdict=case["expected_verdict"],
            confidence=decision.confidence,
            latency_ms=elapsed,
            warnings=decision.warnings,
        ))
    return rows


def report(rows: List[Row]) -> dict:
    scored_retrieval = [r for r in rows if r.retrieval_ok is not None]
    with_citations = [r for r in rows if r.retrieval_ok is not None]
    latencies = sorted(r.latency_ms for r in rows)

    def pct(n, d):
        return round(n / d, 3) if d else None

    return {
        "cases": len(rows),
        "routing_accuracy": pct(sum(r.action_ok for r in rows), len(rows)),
        "verdict_accuracy": pct(sum(r.verdict_ok for r in rows), len(rows)),
        "retrieval_hit_rate": pct(sum(bool(r.retrieval_ok) for r in scored_retrieval),
                                  len(scored_retrieval)),
        "grounded_citation_rate": pct(sum(r.grounded_ok for r in with_citations),
                                      len(with_citations)),
        "held_for_human": sum(r.verdict == Verdict.HOLD.value for r in rows),
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)], 1),
    }


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Score the golden set")
    parser.add_argument("--queries", type=Path,
                        default=REPO_ROOT / "data" / "test_queries.json")
    parser.add_argument("--out", type=Path, help="write the summary as JSON")
    args = parser.parse_args(argv)

    cases = json.loads(args.queries.read_text(encoding="utf-8"))
    rows = evaluate(cases)

    print(f"{'id':<5} {'verdict':<7} {'want':<7} {'route':<5} {'ret':<4} {'grnd':<5} "
          f"{'conf':<5} {'ms':>7}  note")
    for row in rows:
        mark = lambda ok: "ok" if ok else "FAIL"  # noqa: E731
        retrieval = "-" if row.retrieval_ok is None else mark(row.retrieval_ok)
        print(f"{row.id:<5} {row.verdict:<7} {row.expected_verdict:<7} "
              f"{mark(row.action_ok):<5} {retrieval:<4} {mark(row.grounded_ok):<5} "
              f"{row.confidence:<5} {row.latency_ms:>7.1f}  {row.note[:58]}")

    summary = report(rows)
    print()
    for key, value in summary.items():
        print(f"  {key:<24} {value}")

    failures = [r.id for r in rows if not (r.action_ok and r.verdict_ok)]
    if failures:
        print(f"\nfailing cases: {', '.join(failures)}")

    warned = {w for r in rows for w in r.warnings}
    if warned:
        print("\nwarnings surfaced across the run (each one lowers confidence):")
        for warning in sorted(warned):
            print(f"  - {warning}")

    if args.out:
        args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
