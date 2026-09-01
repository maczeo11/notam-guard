# Architecture

## What the system is

A gate in front of drone dispatch. It answers one question — may this flight plan
launch? — and its correctness property is asymmetric: a wrong `BLOCK` costs a
mission, a wrong `ALLOW` costs an aircraft. Everything below follows from that.

## The state machine

`src/graph.py` compiles a LangGraph `StateGraph` with five nodes.

```
        ┌─ retrieve ──→ retriever ──────────────────┐
router ─┼─ both ──────→ retriever ──→ validator ────┼──→ safety ──→ responder ──→ END
        └─ act ────────────────────→ validator ─────┘
```

| Node | Responsibility | Can it set a verdict? |
|---|---|---|
| `router` | Picks `retrieve` / `act` / `both` via `LLMPort.route` | no |
| `retriever` | Top-k chunks from the vector store | no |
| `validator` | Haversine + ceiling checks over parsed NOTAMs | produces `violation`, not the verdict |
| `safety` | Grounds citations, applies policy, opens a ticket | **yes — the only node that does** |
| `responder` | Renders the operator-facing sentence | no |

Branching is done with `add_conditional_edges`, so the router's output selects the
next node rather than being computed and discarded. `_after_router` and
`_after_retriever` are plain functions and are covered by tests in
`tests/test_graph.py`.

`safety` runs *before* `responder` deliberately. The language model is handed a
finished decision and asked to phrase it, so there is no point in the pipeline where
its output could change an outcome.

If LangGraph is not installed, `_SequentialGraph` mirrors the same branching, so the
eval and tests run without the dependency. Only `ImportError` triggers the fallback —
every other exception during compilation is a bug and is raised.

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
| `VectorStorePort` | `PgVectorAdapter` | `InMemoryVectorAdapter` (IDF lexical) |
| `MemoryPort` | `RedisMemoryAdapter` | `InMemoryMemoryAdapter` |
| `TicketPort` | `RedisTicketAdapter` (`SET NX`) | `InMemoryTicketAdapter` (lock) |
| `NotamRepositoryPort` | `FileNotamRepository` | `InMemoryNotamRepository` |
| `LLMPort` | `GroqLLMAdapter`, `OllamaLLMAdapter` | `RuleLLMAdapter` |

`container.override(...)` injects doubles; `container.reset()` clears them. The
autouse fixture in `tests/conftest.py` does both around every test, which is why the
suite needs no Postgres, Redis or API key.

## Safety policy

One function — `src/core/safety.py::finalise`.

```
retrieval failed          → HOLD, confidence 0.0
violation                 → BLOCK, requires_human, confidence = 0.95 − penalties
otherwise                 → confidence = 1.00 − penalties
  confidence < 0.75       → HOLD, requires_human
  else                    → ALLOW
```

Penalties are countable and named, so any confidence the API returns can be derived
from the warnings in the same response:

- **−0.15** per restriction that could not be evaluated (a NOTAM with no coordinates,
  a route that consulted no corpus, an unreadable NOTAM source).
- **−0.40** per citation not found in any retrieved chunk.

A `BLOCK` is never downgraded by weak evidence — only made less confident. The
0.75 threshold is set so that a single unevaluable NOTAM (0.85) still clears, while a
flight that was never cross-checked against the corpus (0.70) does not.

## Grounding

`validator` reports the references it applied (`CAR §7`, `NOTAM 09/03`).
`citations.ground` looks for each one in the retrieved chunks, matching on the
distinctive part so `CAR §7` matches a chunk written as `§7 Micro RPA`. The result is
a `Citation(ref, grounded, excerpt)` per reference, returned to the client in
`evidence`. An ungrounded citation costs 0.40 confidence, which alone is enough to
turn an `ALLOW` into a `HOLD`.

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
49 deduped.

## Failure modes

| Failure | Response |
|---|---|
| Vector store unreachable | `RetrievalUnavailable` → `HOLD`, confidence 0.0, ticket opened |
| Corpus not ingested (empty result) | same — an empty store is a failure, not a clear sky |
| NOTAM directory missing | `NotamSourceUnavailable` → airspace unassessed → warning → `HOLD` |
| NOTAM without coordinates | parsed, kept, reported as unevaluable, −0.15 confidence |
| NOTAM outside its validity window | excluded by `Notam.is_active` at the flight's scheduled time |
| NOTAM with unparseable dates | treated as **active** — failing to read a window must not retire a restriction |
| LLM provider down | `RuleLLMAdapter` fallback; verdict is unaffected because the LLM never set it |
| Redis down | in-process memory and tickets; logged as a warning |

## Observability

`src/core/tracing.py` exposes `@traced(name)`, a real `langsmith.traceable` when
`LANGCHAIN_TRACING_V2` is set and a no-op otherwise. Every graph node carries it, so
a trace shows the branch taken and the per-node timing. `state["latency_ms"]` records
each stage independently of the tracer.

## Deliberate non-goals

- No authentication or multi-tenancy.
- No terrain, weather, airspace class or traffic deconfliction.
- No fleet orchestration — this decides whether one flight may launch, nothing more.
- No VLM. Aerial imagery analysis would be a different system.
