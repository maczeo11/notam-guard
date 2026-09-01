# Evaluation

## Running it

```bash
VECTOR_ADAPTER=memory LLM_ADAPTER=rule python src/eval.py
python src/eval.py --out eval.json          # machine-readable summary
python -m pytest                            # 72 tests
```

The harness scores `data/test_queries.json` at a fixed instant
(`2026-09-02T12:00Z`, inside NOTAM 09/03's validity window) so results do not drift
with the wall clock. It exits non-zero if any case fails.

## Current numbers

```
  cases                    16
  routing_accuracy         1.0
  verdict_accuracy         1.0
  retrieval_hit_rate       1.0
  grounded_citation_rate   1.0
  held_for_human           2
  p50_ms                   2.3
  p95_ms                   1948.0
```

`p95` is the first call, which pays for LangGraph compilation. Steady-state is p50.

## What each number does and does not mean

**`verdict_accuracy` is a regression test, not a claim about AI.** Verdicts come from
`validate_flight` — `alt > 120`, haversine against NOTAM circles. The golden set was
written from those same thresholds. Scoring 1.0 means the boundary arithmetic still
behaves as specified after a refactor. It is worth having for exactly that reason and
worth nothing as evidence that retrieval works.

**`retrieval_hit_rate` is measured over 8 chunks.** The corpus is a 5-clause DGCA
extract plus 3 NOTAMs. At that size a lexical scorer finds the right chunk almost
always. This number will drop on a real corpus and that is the point of tracking it;
quoting 1.0 as a retrieval quality result would be misleading.

**`grounded_citation_rate` is the one that can fail.** It checks that the reference
the verdict rests on was actually present in the retrieved text. The graph tests
force it to fail by injecting a retriever that returns an unrelated clause, and assert
that the flight is then held.

**`routing_accuracy` measures the branch, not the model.** With `LLM_ADAPTER=rule` it
scores a deterministic keyword router. With `LLM_ADAPTER=groq` the same set scores the
model's routing, and the two are worth comparing.

They are reported separately on purpose: a single blended score would let perfect
arithmetic hide a broken retriever.

## What the golden set covers

16 cases in `data/test_queries.json`, each with `expected_action` and
`expected_verdict`:

- **Both sides of every threshold** — 119/120/121m against the DGCA ceiling, 99/100/101m
  against the crane NOTAM. Off-by-one errors here are the ones that matter.
- **Radius boundaries** — 0.15km inside the crane's 1km circle, 1.53km outside it, 5.4km away.
- **Precedence** — above 120m the citation must be `CAR §7`, not the nearest crane.
- **Advisory handling** — the bird-activity NOTAM is reported and must not block.
- **The `act` route** — a flight plan with no regulatory question retrieves nothing
  and is therefore held, not allowed.

## Cases the pytest suite covers instead

Some failure modes cannot be expressed as a golden query because they require
breaking a dependency. Those live in `tests/`:

| Behaviour | Test |
|---|---|
| Dead vector store → `HOLD`, never `ALLOW` | `test_graph.py::test_retrieval_failure_holds_the_flight_and_never_allows` |
| Retrieved text does not support the citation → `HOLD` | `test_graph.py::test_unsupported_citation_downgrades_the_allow_to_a_hold` |
| 50 concurrent creates → 1 ticket, 49 deduped | `test_ticket_idempotency.py` |
| Dedupe window rolls over at midnight | `test_ticket_idempotency.py::test_the_window_rolls_over_the_next_day` |
| NOTAM validity window is inclusive of its final day | `test_notam_parser.py` |
| NOTAM with unparseable dates stays active | `test_notam_parser.py::test_notam_without_a_window_is_treated_as_active` |
| A `BLOCK` is never downgraded by weak evidence | `test_citations_and_safety.py` |
| Flight scheduled after a NOTAM expires is cleared | `test_api.py::test_notam_window_is_evaluated_against_the_scheduled_time` |

## Warnings surfaced by the run

Every case in the golden set carries at least one:

```
- NOTAM 09/04 states a restriction but no usable coordinates/radius
  — could not be evaluated geometrically
- verdict not cross-checked against the retrieved corpus (route=act)
```

The first is real: NOTAM 09/04 in `data/notams/` declares a 5km no-fly zone and gives
no position, so no geometric check can be run against it. Every decision reports it
and pays 0.15 confidence for it. That is the intended behaviour — the alternative is
dropping a no-fly zone silently.

## Known gaps

- 16 cases over 8 chunks is a smoke test, not an evaluation. A real one needs a full
  DGCA CAR and a NOTAM feed.
- No adversarial retrieval cases (near-duplicate NOTAMs, superseded records).
- The recurring-schedule field (`0600-1800 UTC`) is parsed as part of the date range
  rather than as a daily window, so NOTAM 09/04 reads as active for whole days.
- No latency measurement against real pgvector with embeddings; the reported p50 is
  the lexical path.
