# Architecture

## What the system is

A gate in front of drone dispatch. It answers one question — may this flight plan
launch? — and its correctness property is asymmetric: a wrong `BLOCK` costs a
mission, a wrong `ALLOW` costs an aircraft. Everything below follows from that.

## The state machine

`src/graph.py` compiles a LangGraph `StateGraph` with five nodes.

```
        ┌─ retrieve ──→ retriever ───────────────────┐
router ─┼─ both ──────→ validator ──→ retriever ─────┼──→ safety ──→ responder ──→ END
        └─ act ───────→ validator ───────────────────┘
```

| Node | Responsibility | Can it set a verdict? |
|---|---|---|
| `router` | Picks `retrieve` / `act` / `both` via `LLMPort.route` | no |
| `validator` | Haversine + ceiling checks over parsed NOTAMs | produces `violation`, not the verdict |
| `retriever` | Similarity top-k for context, plus an exact `lookup` of the rules the validator applied | no |
| `safety` | Grounds citations, applies policy, opens a ticket | **yes — the only node that does** |
| `responder` | Renders the operator-facing sentence | no |

Branching is done with `add_conditional_edges`, so the router's output selects the
next node rather than being computed and discarded. `_after_router` and
`_after_validator` are plain functions and are covered by tests in
`tests/test_graph.py`.

On the `both` route the validator runs *before* the retriever, so the retriever knows
which rules were applied and can fetch them by name (see Grounding).

**A route that skips a check does not clear the flight.** The `retrieve` route never
runs the validator, and the `act` route retrieves nothing. `safety` treats both as hold
conditions (see Safety policy), so a router that misroutes a flight plan, whether a
language model or a keyword rule, can make a decision *less* certain but cannot make
it *cleared*.

`safety` runs *before* `responder` deliberately. The language model is handed a
finished decision and asked to phrase it, so there is no point in the pipeline where
its output could change an outcome.

`langgraph` is a hard dependency. There is no fallback runner: a graph that is not the
graph under test is not worth having.

## State

`State` is a `TypedDict` with three groups: the request (`lat, lon, alt, drone_id,
query, at`), the evidence gathered (`retrieved, retrieval_failed, validated,
violation, refs, citations, advisories, warnings`), and the outcome (`verdict,
reason, narrative, confidence, requires_human, ticket_id, latency_ms`). Nodes return
partial dicts; LangGraph merges them. Every key a node writes is declared — an
undeclared key would be dropped by the framework.

## Ports and adapters

Five ports in `src/core/ports.py`, resolved through `src/core/container.py`:

| Port | Real adapter | Test double / fallback |
|---|---|---|
| `VectorStorePort` (`search`, `lookup`) | `PgVectorAdapter` | `InMemoryVectorAdapter` (IDF lexical) |
| `MemoryPort` | `RedisMemoryAdapter` | `InMemoryMemoryAdapter` |
| `TicketPort` | `RedisTicketAdapter` (`SET NX`) | `InMemoryTicketAdapter` (lock) |
| `NotamRepositoryPort` | `FileNotamRepository` | `InMemoryNotamRepository` |
| `LLMPort` | `GroqLLMAdapter` | `RuleLLMAdapter` |

`container.override(...)` injects doubles; `container.reset()` clears them. The
autouse fixture in `tests/conftest.py` does both around every test, which is why the
suite needs no Postgres, Redis or API key.

## Safety policy

One function — `src/core/safety.py::finalise`.

```
retrieval failed          → HOLD, confidence 0.0
no flight plan validated  → HOLD, confidence 0.0     (the validator never ran, or the NOTAM source was unreadable)
violation                 → BLOCK, requires_human, confidence = 0.95 − penalties
otherwise                 → confidence = 1.00 − penalties
  nothing was retrieved   → HOLD, requires_human     (regardless of the number)
  confidence < 0.75       → HOLD, requires_human
  else                    → ALLOW
```

Two kinds of defect are handled differently on purpose.

**A check that did not happen is a hold condition.** If nothing was validated or
nothing was retrieved to ground the verdict, the flight is held outright. This does not
depend on the penalty arithmetic landing under the gate, so changing a penalty, or the
gate itself, cannot quietly reopen it. (An earlier version priced these as −0.15 each
and held only because a second, unrelated warning happened to push the total under
0.75. See `tests/test_graph.py`, which removes that second warning.)

**Evidence that is weaker than it should be is a deduction.** Penalties are countable
and named, so any confidence the API returns can be derived from the warnings in the
same response:

- **−0.15** per restriction that could not be evaluated (a NOTAM with no coordinates).
- **−0.40** per citation not defined in any retrieved chunk.
- **−0.40** when nothing was retrieved. This shows up in the number; the hold above is
  what enforces it.

A `BLOCK` is never downgraded by weak evidence — only made less confident. The
0.75 threshold is set so that a single unevaluable NOTAM (0.85) still clears.

## Grounding

`validator` reports the references it applied (`CAR §7`, `NOTAM 09/03`).
`citations.ground` looks for each one in the retrieved chunks, and a reference counts
as grounded only where a chunk **defines** it: at the start of the chunk or of a
sentence inside it, and as a whole number. So `CAR §7` is grounded by a chunk that
begins `§7 Micro RPA`, **not** by the crane NOTAM that says "DGCA CAR §7 applies", and
not by `§70`. `citations.find_definition` is the one rule; grounding, the store's
`lookup` and the evaluation all call it. The result is a `Citation(ref, grounded,
excerpt)` per reference, returned to the client in `evidence`, with the excerpt starting
at the definition. An ungrounded citation costs 0.40 confidence, which alone is enough
to turn an `ALLOW` into a `HOLD`.

Because the check is strict, retrieval has to supply the right chunk. Similarity search
ranks by meaning, and an identifier like `§7` carries almost none: on 2 of the 14 cited
golden-set queries the lexical retriever ranks `§7` outside the top 3. So the retriever
also calls `VectorStorePort.lookup(refs)`, an exact fetch of the chunks that define the
rules the validator applied, and lists them first. Both adapters implement it; a store
that does not returns nothing and the flight is held.

This is falsifiable, and `tests/test_graph.py::test_unsupported_citation_downgrades_the_allow_to_a_hold`
falsifies it deliberately by injecting a retriever that returns an unrelated clause.

## Idempotent tickets

Key: `sha256(drone_id | notam_id | YYYY-MM-DD)[:12]`. The daily window means a
restriction still in force tomorrow gets a fresh ticket, while a dispatcher retrying
this afternoon does not.

`RedisTicketAdapter` uses `SET key ticket_id NX EX 86400` — one atomic step, so
exactly one caller wins and every other receives the winner's id.
`InMemoryTicketAdapter` uses a `threading.Lock` for the same guarantee in-process.
`tests/test_ticket_idempotency.py` runs 50 concurrent creates and asserts 1 created,
49 deduped, and `tests/test_redis_adapters.py` runs the same check through the Redis
adapter with one client per thread (the shape of several API processes sharing one
Redis). Set `REDIS_TEST_URL` to run it against a real server as well.

`approve` is first-wins: it runs under `WATCH`, so two approvers racing cannot both
write, and approving an already-approved ticket returns it unchanged. The write keeps
the ticket's TTL. The approver is a self-asserted string, since the API has no
authentication.

## Failure modes

| Failure | Response |
|---|---|
| Vector store unreachable | `RetrievalUnavailable` → `HOLD`, confidence 0.0, ticket opened |
| Corpus not ingested (empty result) | same — an empty store is a failure, not a clear sky |
| NOTAM directory missing | `NotamSourceUnavailable` → nothing validated → `HOLD`, confidence 0.0 |
| Router sends a flight plan down `retrieve` | Validator never runs → nothing validated → `HOLD`, confidence 0.0 |
| `act` route (nothing retrieved) | Not cross-checked → `HOLD`, whatever the confidence number says |
| Lookup of the applied rules fails | Same as a failed search: `RetrievalUnavailable` → `HOLD` |
| NOTAM without coordinates | parsed, kept, reported as unevaluable, −0.15 confidence |
| NOTAM outside its validity window | excluded by `Notam.is_active` at the flight's scheduled time |
| NOTAM with unparseable dates | treated as **active** — failing to read a window must not retire a restriction |
| LLM provider down | `RuleLLMAdapter` fallback; verdict is unaffected because the LLM never set it |
| Redis down | in-process memory and tickets; logged as a warning |

## Observability

`src/core/tracing.py` exposes `@traced(name)`, a real `langsmith.traceable` when
tracing is enabled and a no-op otherwise. Every graph node carries it, so a trace
shows the branch taken and the per-node timing. `state["latency_ms"]` records each
stage independently of the tracer.

Both `LANGSMITH_*` (current) and `LANGCHAIN_*` (legacy) variable names are read,
since the SDK honours both and checking only one silently disables tracing for
anyone following the current documentation. A missing or placeholder key disables
tracing with one warning instead of a `403` per span.

## Interface

`web/` is a Vite + React map interface at `localhost:5173`, proxying `/api` to the
service. It exists to make the parts of the decision that are usually invisible
inspectable: each citation's grounded state and supporting excerpt, the retrieved
chunks with the matched reference highlighted, confidence drawn against the 0.75
gate, and unevaluable restrictions listed apart from advisories.

The highlighting in `web/src/lib/verdict.ts` (`findDefinition`) mirrors
`core/citations.py::find_definition`, so the interface marks the place a reference is
*defined*, which is what the backend grounded on, rather than every mention of it.
`web/src/lib/scenarios.ts` holds four preset flight plans covering every verdict the
gate can return.

## Deliberate non-goals

- No authentication or multi-tenancy.
- No terrain, weather, airspace class or traffic deconfliction.
- No fleet orchestration — this decides whether one flight may launch, nothing more.
- No VLM. Aerial imagery analysis would be a different system.
