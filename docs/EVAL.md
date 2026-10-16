# Evaluation

## Running it

```bash
VECTOR_ADAPTER=memory LLM_ADAPTER=rule python src/eval.py
python src/eval.py --out eval.json          # machine-readable summary
python -m pytest                            # 126 passed, 1 skipped (live Redis, needs REDIS_TEST_URL)
```

The harness scores `data/test_queries.json` at a fixed instant
(`2026-09-02T12:00Z`, inside the sample NOTAMs' validity windows) so results do not
drift with the wall clock. It exits non-zero if a verdict or route is wrong.
`tests/test_sample_data.py` checks that the instant is inside those windows and that the
windows have not lapsed.

## Current numbers

```
  cases                    16
  routing_accuracy         1.0
  verdict_accuracy         1.0
  retrieval_hit_rate       0.857
  grounded_citation_rate   1.0
  held_for_human           2
  p50_ms                   ~3
  p95_ms                   ~3800
```

`p95` is the first call, which pays for LangGraph compilation. Steady-state is p50.

`retrieval_hit_rate` is **0.857** (12 of 14 cited cases) on purpose, and it is the most
informative number here. It scores *similarity search on its own*: did the top 3 for the
case's query include the chunk that **defines** the expected reference? On Q08 and Q15
the lexical retriever ranks the §7 clause outside the top 3, because an identifier like
`§7` carries almost no weight in a word-overlap score. The gate does not suffer for it,
since the graph also fetches cited rules by identifier (`lookup`), which is why
`grounded_citation_rate` is 1.0. Keeping the two apart is the reason they are separate
numbers.

## What each number does and does not mean

**`verdict_accuracy` is a regression test, not a claim about AI.** Verdicts come from
`validate_flight` — `alt > 120`, haversine against NOTAM circles. The golden set was
written from those same thresholds. Scoring 1.0 means the boundary arithmetic still
behaves as specified after a refactor. It is worth having for exactly that reason and
worth nothing as evidence that retrieval works.

**`retrieval_hit_rate` is measured over 8 chunks.** The corpus is a title line and
four DGCA clauses (§7, §8, §9, §12) plus 3 NOTAMs. At that size a lexical scorer
should find the right chunk almost always, and it still misses 2 of 14. This number
will drop further on a real corpus and that is the point of tracking it.

**`grounded_citation_rate` is the one that can fail.** It checks that the reference
the verdict rests on was *defined* by the retrieved text, not just mentioned in it.
It is a gate-level number: it includes the identifier lookup, so it can be 1.0 while
`retrieval_hit_rate` is not. For a decision with no citations it is vacuously true.
The graph tests force it to fail by injecting a retriever that returns an unrelated
clause, and assert that the flight is then held.

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
  and is therefore held, not allowed (confidence 0.45: −0.15 for the unevaluable
  NOTAM 09/04 and −0.40 for the missing cross-check). The hold itself does not depend
  on that number; `test_the_act_route_is_held_even_when_no_other_warning_exists`
  removes every other warning and still expects `HOLD`.

## Cases the pytest suite covers instead

Some failure modes cannot be expressed as a golden query because they require
breaking a dependency. Those live in `tests/`:

| Behaviour | Test |
|---|---|
| Dead vector store → `HOLD`, never `ALLOW` | `test_graph.py::test_retrieval_failure_holds_the_flight_and_never_allows` |
| Retrieved text does not support the citation → `HOLD` | `test_graph.py::test_unsupported_citation_downgrades_the_allow_to_a_hold` |
| Router sends a flight plan down `retrieve` → `HOLD`, not `ALLOW` | `test_graph.py::test_a_misrouted_request_is_held_not_cleared` |
| Unreadable NOTAM source → `HOLD`, confidence 0 | `test_graph.py::test_an_unreadable_notam_source_holds_the_flight` |
| A chunk that only mentions §7 does not ground §7 | `test_citations_and_safety.py::test_a_chunk_that_only_mentions_a_rule_does_not_ground_it` |
| The applied rule is fetched by identifier, not left to similarity | `test_graph.py::test_the_rule_that_was_applied_is_fetched_by_name_not_left_to_similarity`, `test_lookup.py` |
| Overlapping breaches cite every NOTAM, order-independent | `test_tools.py::test_the_most_restrictive_breach_is_reported_and_every_breach_is_cited` |
| Router matches whole words (`scarce` is not `car`) | `test_llm_router.py` |
| 50 concurrent creates → 1 ticket, 49 deduped (in-process lock) | `test_ticket_idempotency.py` |
| 50 concurrent creates through separate Redis clients → 1 ticket | `test_redis_adapters.py` |
| The first approval stands, under concurrency | `test_redis_adapters.py::test_concurrent_approvals_leave_exactly_one_approver` |
| Sample NOTAM windows have not lapsed | `test_sample_data.py` |
| Dedupe window rolls over at midnight | `test_ticket_idempotency.py::test_the_window_rolls_over_the_next_day` |
| NOTAM validity window is inclusive of its final day | `test_notam_parser.py` |
| NOTAM with unparseable dates stays active | `test_notam_parser.py::test_notam_without_a_window_is_treated_as_active` |
| A `BLOCK` is never downgraded by weak evidence | `test_citations_and_safety.py` |
| Flight scheduled after a NOTAM expires is cleared | `test_api.py::test_notam_window_is_evaluated_against_the_scheduled_time` |

## Warnings surfaced by the run

Every case in the golden set carries the first; the two `act`-route cases also carry
the second:

```
- NOTAM 09/04 states a restriction but no usable coordinates/radius
  — could not be evaluated geometrically
- verdict not cross-checked against the retrieved corpus — nothing was retrieved to ground it
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
  the lexical path. `PgVectorAdapter` (including `lookup`) is tested against a fake
  connection, not a live Postgres.
- The golden set pins one instant. Behaviour at other times is covered by
  `tests/test_sample_data.py` and the scheduled-time tests, not by the 16 cases.
