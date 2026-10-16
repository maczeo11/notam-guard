# NOTAM-Guard: Design Document

- Version: 0.2.0 (prototype)
- Author: Komma Bhanu Teja
- Last updated: 2026-10-14
- Code: https://github.com/maczeo11/notam-guard

NOTAM-Guard decides whether a drone flight may launch. You give it a position, an altitude and a drone id, and it answers `ALLOW`, `BLOCK` or `HOLD`, along with the rule it relied on and the text of that rule.

This document has two parts. The first (sections 1 to 12) is the high-level design: what the system is for, how it is put together and why. The second (sections 13 to 26) is the low-level design: the types, contracts, algorithms, API and storage.

The system is a working prototype. The decision logic, API, tests and web interface are complete. The data is very small (four DGCA clauses and three NOTAMs), and the system has never run against live data. The test suite has 127 tests, of which 126 run by default. The Postgres, Redis and LLM adapters are tested against fakes, not live services. Section 11 covers what that leaves open.

---

# Part 1: High-level design

## 1. Overview

A dispatcher proposes a flight: where, how high above the ground, which drone, and optionally when. The system returns one of three verdicts.

- `ALLOW`: nothing in the rules is breached, and the evidence is good enough to clear the flight without a person looking at it.
- `BLOCK`: a rule is breached. A person always sees this.
- `HOLD`: the system cannot justify a decision, for example because it could not read the regulations. A person always sees this too.

The two kinds of mistake do not cost the same. Blocking a legal flight loses a mission. Allowing an illegal one can lose an aircraft. So the design leans one way: when in doubt, hold.

The obvious way to build this is to retrieve some regulations, ask a language model whether the flight is legal, and print the answer. That fails in the way that matters. If the database is down or the retriever misses, the model still answers, and the answer is a confident `ALLOW`. NOTAM-Guard is built around three ideas that prevent this.

1. Code decides. The verdict comes from distance and altitude arithmetic over parsed NOTAMs. The language model picks a route and words one sentence for the operator. It never produces or changes a verdict.
2. Evidence is shown, not asserted. Every rule the verdict rests on is checked against retrieved text that defines it, and the response includes that text.
3. Failure closes the gate. If a check could not run, or the regulations could not be read, the flight is held. Nothing is filled in with placeholder data.

## 2. Scope

The system covers:

- the DGCA micro-RPA altitude ceiling (CAR §7, 120 m AGL)
- NOTAMs expressed as a circle with an altitude limit and a validity window
- returning the rule that was applied, with the retrieved text that defines it
- a human approval step for every `BLOCK` and `HOLD`

It does not cover terrain, weather, airspace class or traffic. It does not orchestrate fleets: it decides one flight at a time. It has no authentication or multi-tenancy. It does not parse real NOTAM formats such as ICAO Q-codes or recurring schedules. These are limits of the prototype, not claims about what a production system would need, and section 11 returns to them.

## 3. Architecture

```mermaid
flowchart TD
  OP["Dispatcher"] --> WEB["Web UI"]
  EXT["Dispatch system"] --> API
  WEB -->|"/api"| API["FastAPI service"]
  API --> GRAPH["Decision graph (LangGraph)"]
  GRAPH --> FILES[("NOTAM files")]
  GRAPH --> PG[("Postgres + pgvector")]
  GRAPH --> RD[("Redis")]
  GRAPH -.->|"optional"| LLM["Groq LLM"]
  GRAPH -.->|"optional"| LS["LangSmith"]
```

A FastAPI service wraps a five-node LangGraph state machine. The graph reads two kinds of data. Parsed NOTAMs, read from text files, drive the verdict. Regulation text, held in a vector store, is used only to ground citations. Tickets for held and blocked flights, and each drone's recent ticket history, live in Redis. Tickets can instead live in DynamoDB (`TICKET_STORE=dynamodb`).

| Component | What it does | Needed? |
|---|---|---|
| Web UI | Shows the verdict with its evidence and a map of NOTAM circles | No |
| API | Validates input, routes requests, shapes responses | Yes |
| Decision graph | Produces a `Decision` from a flight plan | Yes |
| Vector store | Similarity search for context, and exact lookup of cited rules | Yes. An in-memory lexical store can be chosen by configuration; there is no automatic fallback, and a failed store holds the flight |
| NOTAM repository | Parses NOTAM text into structured records | Yes |
| Redis | Idempotent tickets and drone history | Falls back to in-process storage |
| Groq LLM | Routing and wording | Falls back to a rule-based adapter |
| LangSmith | Per-node traces | Off by default |

The decision logic does not import psycopg2, redis or any LLM SDK. It talks to five abstract ports (vector store, memory, tickets, NOTAM repository, LLM), and each port has a real adapter and an in-process one. This is why the whole test suite runs with no infrastructure, and why the service can start with none of it.

## 4. How a request is decided

```mermaid
flowchart TD
  S(["POST /validate"]) --> R{"router"}
  R -->|"act"| V["validator"]
  R -->|"both"| V
  R -->|"retrieve"| T["retriever"]
  V -->|"both"| T
  V -->|"act"| SF["safety"]
  T --> SF
  SF --> RS["responder"]
  RS --> E(["response"])
```

The graph has five nodes.

- The router chooses a route: `retrieve`, `act` or `both`.
- The validator runs the arithmetic: it checks the altitude ceiling and the NOTAM circles, and records which rules it applied.
- The retriever fetches regulation text: similarity search for context, plus an exact lookup of the rules the validator applied.
- The safety node grounds the citations, applies the safety policy and opens a ticket when a person has to look. It is the only node that sets a verdict.
- The responder turns the finished decision into one sentence for the operator.

The safety node runs before the responder. The model is handed a decision that is already final and asked to phrase it, so nothing it writes can change the outcome.

The three routes differ in which checks happen.

| Route | Path | Outcome |
|---|---|---|
| `both` | router, validator, retriever, safety, responder | The full check |
| `act` | router, validator, safety, responder | Nothing retrieved to ground the verdict, so the flight is held unless it is breached |
| `retrieve` | router, retriever, safety, responder | The validator never ran, so the flight is always held |

On the `both` route the validator runs before the retriever, so the retriever knows which rules were applied and can fetch them by name. The router's choice is a real branch in the graph, not a value that is computed and then ignored.

```mermaid
sequenceDiagram
  participant C as Client
  participant G as API and graph
  participant L as LLM
  participant D as NOTAMs and vector store
  participant T as Tickets
  C->>G: POST /validate
  G->>L: route
  L-->>G: both
  G->>D: NOTAMs in force
  D-->>G: parsed NOTAMs
  Note over G: validate_flight finds a breach
  G->>D: search and lookup
  D-->>G: chunks
  Note over G: ground, then finalise gives BLOCK
  G->>T: create ticket
  T-->>G: ticket id
  G->>L: word the decision
  L-->>G: one sentence
  G-->>C: verdict, evidence, ticket_id
  C->>G: POST /approve
```

## 5. The safety policy

One function, `finalise` in `src/core/safety.py`, turns the validator's result and the evidence into a final verdict.

```mermaid
flowchart TD
  S(["finalise"]) --> Q1{"retrieval failed?"}
  Q1 -->|"yes"| H0["HOLD, confidence 0.00, human"]
  Q1 -->|"no"| Q2{"flight plan validated?"}
  Q2 -->|"no"| H0
  Q2 -->|"yes"| P["confidence = base minus penalties"]
  P --> Q3{"violation found?"}
  Q3 -->|"yes"| B["BLOCK, human"]
  Q3 -->|"no"| Q4{"something retrieved, and confidence at least 0.75?"}
  Q4 -->|"no"| H1["HOLD, human"]
  Q4 -->|"yes"| A["ALLOW, no human"]
```

Two different problems are handled in two different ways.

If a check did not happen, the flight is held outright. That covers a plan that was never validated, and a verdict with nothing retrieved to ground it. These are not priced as deductions, because a deduction only holds the flight while the arithmetic happens to land under the gate. An earlier version priced them as small deductions and held an unchecked plan only because an unrelated warning added a second one. Now the hold does not depend on the number at all.

If the evidence is merely weaker than it should be, confidence goes down. Confidence starts at 1.00 for a clear flight and 0.95 for a violation, and each named defect takes something off.

| Defect | Cost |
|---|---|
| A restriction the parser could not evaluate (a NOTAM with no coordinates) | 0.15 each |
| A cited rule that no retrieved chunk defines | 0.40 each |
| Nothing was retrieved at all | 0.40 once |

An `ALLOW` needs confidence of at least 0.75. A single unevaluable NOTAM (0.85) still clears, while a single ungrounded citation (0.60) does not. A `BLOCK` is never downgraded by weak evidence, only made less confident, since blocking is the safe direction. It still always goes to a person, because refusing a mission has a cost too.

Because the penalties are named and countable, any confidence value in a response can be rebuilt from the `warnings` and `evidence` in the same response. Some worked cases:

| Situation | Result |
|---|---|
| Crane breach, NOTAM 09/04 in force | `BLOCK` at 0.80 (0.95 minus 0.15) |
| Clear flight, NOTAM 09/04 in force | `ALLOW` at 0.85 |
| No regulatory wording in the query, so the `act` route | `HOLD` at 0.45 (1.00 minus 0.15 minus 0.40) |
| Router sends a 500 m flight down `retrieve` | `HOLD` at 0.00, ticket opened |
| Cited rule defined in no retrieved chunk | `HOLD` at 0.60 |
| `BLOCK` with an ungrounded citation and one unevaluable NOTAM | `BLOCK` at 0.40 |

## 6. Data

The same source files are used in two ways, and the difference matters.

The first use is structured. A parser reads each NOTAM line into coordinates, a radius, an altitude limit, a validity window and a severity. This drives the verdict. The second use is text. The files are cut into one chunk per line and indexed for retrieval. This is used for grounding: proving that the rule the verdict cites actually appears in retrieved text. Retrieval never decides the verdict. It decides whether the system can show what it relied on.

The corpus is small:

- `data/dgca_car.txt` holds a title line and four clauses: §7 (micro RPA, 120 m), §8 (nano RPA), §9 (distance from airports and obstacles) and §12 (battery safety).
- `data/notams/notam_0903_crane.txt`: NOTAM 09/03, a crane with a 100 m limit and a 1 km radius around 18.53, 73.84.
- `data/notams/notam_0904_runway.txt`: NOTAM 09/04, a runway closure with a 5 km no-fly zone and no coordinates. It is deliberately unplaceable, to exercise the "could not be evaluated" path.
- `data/notams/notam_0905_bird.txt`: NOTAM 09/05, bird activity with no stated limit. It is an advisory.

That is 8 chunks. The in-memory store and the ingest command both produce exactly these 8. The validity windows on the two restrictive NOTAMs are fictional and run to 2027-12-31, so the demo keeps behaving as documented. A test fails 60 days before they lapse.

Postgres with pgvector holds the chunks and their 384-dimension embeddings. Redis holds tickets, their dedupe keys and each drone's last five tickets. The NOTAM files are read and parsed on first use and cached.

## 7. Failure handling

The rule is that retrieval may not degrade quietly, while the other dependencies may. Redis, the LLM and tracing are conveniences. The regulations are evidence.

| What goes wrong | What happens |
|---|---|
| Vector store unreachable, or returns nothing | `HOLD`, confidence 0. This applies even if the geometry shows a violation |
| The exact lookup of applied rules fails | The same |
| NOTAM source missing or empty | Nothing is validated, so `HOLD`, confidence 0 |
| Router sends a plan down `retrieve` | The validator never runs, so `HOLD`, confidence 0 |
| `act` route, nothing retrieved | Held (or `BLOCK` if breached), whatever the confidence says |
| A restrictive NOTAM has no coordinates | Kept, reported as a warning on every decision, 0.15 off confidence |
| A NOTAM is outside its window at the flight time | Left out |
| A NOTAM's dates cannot be parsed | Treated as active, because failing to read a window must not retire a restriction |
| LLM provider fails or returns an unusable route | The rule-based adapter takes over. The verdict is unaffected |
| Redis unreachable | Tickets and history become process-local, with a warning. Dedupe then stops spanning processes |
| DynamoDB refuses or throttles a ticket write | `TicketStoreUnavailable`. The verdict is returned unchanged with a warning and no ticket, so the flight stays held, and `/approve` returns 503. If the table cannot be reached at start, tickets become process-local, with an error in the log |
| Tracing key missing or a placeholder | Tracing is switched off with one warning |

## 8. Design decisions

**The model routes and words. It does not decide.** A language model is good at reading a free-text request and bad at being the only thing between a flight plan and a clearance. Giving it the routing and the wording keeps what it is good at and removes what it is not. Because the route decides which checks run, the policy in section 5 treats a skipped check as a hold, so a bad route cannot clear a flight.

**A skipped check holds the flight; it does not cost points.** This is the lesson of the first version of the policy. When skipped checks were deductions, the safety of the system depended on the sizes of unrelated penalties. Making them hold conditions removes that coupling, and a test removes every other warning and still expects the hold.

**A citation must be defined, not mentioned.** The crane NOTAM says "DGCA CAR §7 applies". If any chunk containing `§7` grounded the rule, that sentence alone would stand in for the text of §7. So a reference is grounded only where it begins a chunk or a sentence, as a whole number: `§7` is defined by "§7 Micro RPA ..." and not by "...CAR §7 applies" or by `§70`.

**Cited rules are looked up by name.** Once grounding requires a definition, retrieval has to supply the right chunk. Similarity search is a poor fit for that. An identifier like `§7` carries almost no meaning to a ranker, and on two of the 14 cited golden-set queries the lexical retriever ranks §7 outside the top three. The rules the validator applied are known identifiers, so the retriever fetches them directly and lists them first. Similarity search still supplies context.

**Retrieval quality and gate quality are measured separately.** The evaluation scores similarity search on its own (0.857) and the full gate (1.0). The lookup keeps the second number at 1.0 even though the retriever misses sometimes, and if it were folded into the first it would hide that weakness.

**Ports with real and in-process adapters.** Every port has two implementations. Tests inject the in-process ones, which is why 126 tests run in a few seconds with nothing installed. The cost is a small composition root (`core/container.py`) that every consumer must go through.

**First approval wins.** Closing the human gate twice should not rewrite who closed it. Approval runs under a Redis `WATCH` transaction (or one conditional update in DynamoDB), returns an already-approved ticket unchanged, and keeps the ticket's expiry.

**Sample windows are pinned, and a test watches them.** NOTAMs have validity windows, so sample data that is in force today stops being in force later. That happened: the demo's headline case silently changed from `BLOCK` to `ALLOW` while the documentation still described the old result. The windows now run well ahead, and a test fails 60 days before they end.

## 9. Deployment and configuration

```mermaid
flowchart LR
  subgraph compose["docker compose"]
    WEBC["web: port 5173"] --> APIC["api: port 8000, python 3.11-slim"]
    APIC --> PGC[("postgres: pgvector/pgvector:pg16")]
    APIC --> RDC[("redis: 7-alpine")]
  end
```

There are two ways to run it. With no infrastructure, set `VECTOR_ADAPTER=memory` and `LLM_ADAPTER=rule`: retrieval is lexical, the router is rule-based, and tickets and memory are held in the process. The verdict logic is identical. With the full stack, `docker compose up -d` starts Postgres with pgvector, Redis, the API and the web UI, and `python -m src.ingest` loads the corpus. `railway.json` also points a container build at `Dockerfile.api`, whose image holds `src/` and `data/` only.

All configuration is read in one file, `src/core/config.py` (section 20). Until `src.ingest` has run against a fresh database, retrieval fails and every flight is held. That is intended.

## 10. Testing and evaluation

There are 127 collected tests, with 126 run by default. The one that is skipped talks to a real Redis and runs only when `REDIS_TEST_URL` is set. The suite needs no Postgres, no Redis and no API key. Section 24 lists what each file covers.

A separate evaluation scores 16 golden queries at a fixed instant (2026-09-02 at 12:00 UTC) so the result does not drift with the clock. It reports four numbers.

| Metric | Value | What it measures |
|---|---|---|
| Routing accuracy | 1.0 | Whether the router took the expected branch |
| Verdict accuracy | 1.0 | Whether the arithmetic still gives the expected verdicts. The golden set was written from the same thresholds as the code, so this is a regression check, not a claim about retrieval |
| Retrieval hit rate | 0.857 (12 of 14) | Whether similarity search alone puts the defining chunk in the top three |
| Grounded citation rate | 1.0 | Whether, after the whole graph including the lookup, every citation is grounded |

Sixteen cases over eight chunks is a smoke test, not an evaluation. A real one needs the full DGCA CAR and a NOTAM feed.

## 11. Limitations

- The data is tiny and was not tested at scale.
- Real NOTAM formats are not parsed. A recurring window such as `0600-1800 UTC` is read as part of the date range, so NOTAM 09/04 counts as in force for whole days.
- Coordinates in NOTAM text are read as `lat, lon`, in that order.
- Terrain, weather, airspace class and other traffic are not modelled. Altitude is assumed to be AGL.
- There is no authentication. `/approve` accepts any caller and any approver name.
- Tickets are deduplicated on the day the request is made, not on `scheduled_for`.
- Similarity search uses the request's free-text query. Only the rules the validator applied are fetched by name, and the lexical retriever is weak on identifiers.
- `PgVectorAdapter.lookup` narrows with `ILIKE`, which scans the table. That is fine at this size. A larger corpus should store each chunk's defined reference in an indexed column.
- Postgres is tested through a fake connection, Redis through `fakeredis`, and DynamoDB through moto. The DynamoDB concurrency checks (50 simultaneous creates, 20 simultaneous approvals) have also been run by hand against a real table. The Groq adapter has not been run against a live provider. None of this has run in CI against live services.

If the gate were put in front of an agent that proposes missions, the pieces to change are the NOTAM source (a live feed and a real parser), the altitude check (a terrain-aware AGL source), the approval step (authenticated, with an audit record), and the input (structured mission data, so free text stops steering routing and retrieval). The principle that a skipped check holds the flight matters more in that setting, not less, because an agent will call the gate more often and less carefully than a person at a form.

## 12. Revision notes

Version 0.2.0 was reviewed on 2026-10-14. Writing this document turned up six problems, each reproduced first and fixed with a test that failed before the fix.

1. The `retrieve` route skipped the validator, and a 500 m flight came back `ALLOW` at 0.85. Not validated is now a hold.
2. An unchecked plan was held only because of an unrelated second warning. Nothing retrieved is now a hold of its own.
3. The sample NOTAM windows had lapsed, so the default demo returned different verdicts from the documentation. They were extended and a test now watches them.
4. The ingest command produced 4 chunks while the in-memory store produced 8. Both now cut one chunk per line.
5. Grounding accepted a mention of a rule as if it were the rule. It now requires a definition, and cited rules are fetched by identifier.
6. The Redis adapters had no tests, and approval could race. They now have tests, and approval is first-wins under `WATCH`.

Smaller fixes: overlapping NOTAM breaches are all cited and ordered the same way regardless of input order, advisories listed after a breach are no longer dropped, the router matches whole words so `scarce` no longer counts as `car`, a leading byte-order mark no longer ends up in the first chunk of each file, and `/ticket` and `/approve` now return `approved_by`. As a result the retrieval hit rate dropped from a reported 1.0 to 0.857, because the old figure counted a mention as a hit.

---

# Part 2: Low-level design

## 13. Repository layout

```
src/
  app.py                  FastAPI app, request and response models, endpoints
  graph.py                State schema, five nodes, routing functions, graph build
  tools.py                haversine_km, notams_near, validate_flight (no LLM, no I/O)
  ingest.py               corpus into pgvector (CLI)
  eval.py                 golden-set scorer (CLI)
  core/
    config.py             every environment variable, read once
    domain.py             dataclasses and enums
    ports.py              five abstract ports
    container.py          composition root and test overrides
    notam_parser.py       NOTAM text into Notam
    citations.py          extract references, find definitions, ground them
    safety.py             finalise(): the verdict policy
    chunking.py           chunk_words, chunk_lines
    tracing.py            @traced (LangSmith or no-op)
    errors.py             typed failures
  adapters/
    pgvector_adapter.py   PgVectorAdapter, InMemoryVectorAdapter
    redis_adapter.py      connect(), RedisMemoryAdapter, InMemoryMemoryAdapter
    ticket_adapter.py     RedisTicketAdapter, InMemoryTicketAdapter, dedupe_key
    dynamodb_ticket_adapter.py   DynamoTicketAdapter, connect (TICKET_STORE=dynamodb)
    notam_repository.py   FileNotamRepository, InMemoryNotamRepository
    llm_adapter.py        RuleLLMAdapter, GroqLLMAdapter
data/                     dgca_car.txt, notams/*.txt, test_queries.json, chunks.json
tests/                    11 test files and conftest.py
web/src/                  React and TypeScript UI
docs/                     ARCHITECTURE.md, EVAL.md, SETUP.md, DESIGN.md
```

## 14. Domain model

All of these live in `src/core/domain.py`.

```mermaid
classDiagram
  class FlightPlan {
    +lat float
    +lon float
    +alt int
    +drone_id str
    +query str
    +at datetime
    +when() datetime
  }
  class Notam {
    +notam_id str
    +text str
    +lat float
    +lon float
    +radius_km float
    +max_alt_m int
    +valid_from datetime
    +valid_to datetime
    +severity Severity
    +is_geolocatable() bool
    +is_active(at) bool
  }
  class ValidationResult {
    +violation bool
    +reason str
    +refs list
    +advisories list
    +warnings list
    +notam_id str
  }
  class Citation {
    +ref str
    +grounded bool
    +excerpt str
  }
  class Ticket {
    +ticket_id str
    +key str
    +deduped bool
    +status str
    +approved_by str
  }
  class Decision {
    +verdict Verdict
    +reason str
    +confidence float
    +requires_human bool
    +ticket_id str
    +action Action
  }
  ValidationResult ..> Notam : cites
  Decision "1" o-- "*" Citation
```

Three enums complete the model: `Verdict` is `ALLOW`, `BLOCK` or `HOLD`; `Action` is `retrieve`, `act` or `both`; `Severity` is `restrictive` or `advisory`.

A few rules are worth stating. `FlightPlan.when()` returns `at`, or the current UTC time if `at` is unset. `Notam.is_geolocatable` is true only if `lat`, `lon` and `radius_km` are all present, and `Notam.is_active(at)` is false only when `at` falls outside a bound the NOTAM actually states, so a NOTAM with no window is always active. A `restrictive` NOTAM that is breached is a violation. An `advisory` is reported and never blocks. `ValidationResult` contains no LLM text. `Ticket.status` is `open` or `approved`, and `approved_by` is whatever the caller supplied, since there is no authentication.

## 15. Ports, adapters and the container

```mermaid
flowchart LR
  CORE["graph.py, tools.py, safety.py"]
  CORE --> P1["VectorStorePort"] --> A1["PgVector or InMemory"]
  CORE --> P2["MemoryPort"] --> A2["Redis or InMemory"]
  CORE --> P3["TicketPort"] --> A3["Redis or InMemory"]
  CORE --> P4["NotamRepositoryPort"] --> A4["File or InMemory"]
  CORE --> P5["LLMPort"] --> A5["Groq or Rule"]
```

The decision logic on the left imports no infrastructure. Each port in the middle has a real adapter and an in-process one, on the right.

| Port | Contract |
|---|---|
| `VectorStorePort.search(query, k)` | Up to `k` chunks by similarity. Must raise `RetrievalUnavailable` instead of returning a fallback |
| `VectorStorePort.lookup(refs)` | The chunks that define each reference, found by identifier. Must raise `RetrievalUnavailable` if the store cannot be queried. The default returns nothing, which grounds less and so fails closed |
| `MemoryPort.push_history`, `get_history` | Record a ticket against a drone and return its recent history |
| `TicketPort.create`, `get`, `approve` | `create` is exactly-once per drone, NOTAM and day. `approve` is first-wins |
| `NotamRepositoryPort.active(at)`, `all()` | The NOTAMs in force at `at`, and all of them |
| `LLMPort.route`, `respond` | `route` returns `retrieve`, `act` or `both`. `respond` renders one sentence and never changes the verdict |

`core/container.py` resolves each port once per process and caches the result. `get_vector_store()` returns the in-memory adapter when `VECTOR_ADAPTER=memory`, and the pgvector adapter otherwise. `get_memory()` and `get_ticket_store()` try Redis through `connect()`, which pings with a one-second timeout, and use the in-process adapter if there is no client. `get_llm()` returns the Groq adapter when `LLM_ADAPTER=groq`, and the rule adapter otherwise. `override(**ports)` injects test doubles, `reset()` clears the cache and overrides, and an autouse fixture in `tests/conftest.py` calls both around every test.

## 16. The decision graph

### State

`State` in `src/graph.py` is a `TypedDict(total=False)`. Nodes return partial dictionaries and LangGraph merges them. A key that is not declared would be dropped, so every key a node writes is declared.

- Request: `query`, `lat`, `lon`, `alt`, `drone_id`, `at`
- Routing: `action`
- Evidence: `retrieved`, `retrieval_failed`, `validated`, `violation`, `refs`, `citations`, `advisories`, `warnings`
- Outcome: `verdict`, `reason`, `narrative`, `confidence`, `requires_human`, `ticket_id`, `ticket_deduped`, `history`, `latency_ms`

### Nodes

| Node | Reads | Writes | Notes |
|---|---|---|---|
| `router` | `query`, `lat`, `lon` | `action`, `latency_ms` | `has_coords` is true when both `lat` and `lon` are set. Calls `LLMPort.route` |
| `validator` | the request fields | `validated`, `violation`, `refs`, `reason`, `advisories`, `warnings`, `latency_ms` | Fetches `active(plan.when())` and calls `validate_flight`. On `NotamSourceUnavailable` it returns `validated=False` and a warning that the airspace was not assessed |
| `retriever` | `query`, `refs` | `retrieved`, `retrieval_failed`, `latency_ms` | Calls `search(query, k)`, then `lookup(refs)`. Lists the defining chunks first, then the context chunks, without repeats. If either call raises `RetrievalUnavailable` it returns an empty list and `retrieval_failed=True` |
| `safety` | the evidence and routing keys | `verdict`, `confidence`, `requires_human`, `citations`, `warnings`, `ticket_id`, `ticket_deduped`, `reason` (sometimes), `history` (for a new ticket), `latency_ms` | See below |
| `responder` | `verdict`, `reason`, `citations` | `narrative`, `reason`, `latency_ms` | Calls `LLMPort.respond` |

The safety node works in this order. It grounds the references against whatever was retrieved. It calls `finalise` with `validated` (whether the validator produced a result) and `cross_checked` (whether anything was retrieved). If nothing was validated, `reason` falls back to the validator's reason or "no flight plan evaluated". If the verdict is a `HOLD` caused by a retrieval failure, `reason` becomes a plain statement that retrieval was unavailable and the flight is held. Finally, if a person has to look, it creates a ticket, with severity `HIGH` for a `BLOCK` and `MEDIUM` otherwise, keyed on the first citation's reference, and records new tickets in the drone's history.

### Routing

`_after_router` sends `retrieve` to the retriever and everything else to the validator. A missing `action` defaults to `both`. `_after_validator` sends `both` to the retriever and everything else to safety. The retriever always goes to safety, and safety always goes to the responder.

`build_graph()` compiles the state machine. `langgraph` is a hard dependency and there is no fallback runner. `get_graph()` compiles once per process, and the app's lifespan hook triggers it at startup so the first request does not pay for the compilation.

`to_decision(state)` builds the `Decision`. Its `reason` is the narrative if there is one, and the validator's reason otherwise. With the Groq adapter on, the `reason` string in the API response is written by the model. The verdict, confidence, citations, evidence and warnings are not.

## 17. Algorithms

### Distance

Haversine distance on a sphere of radius 6371.0 km.

```
a = sin(dlat/2)^2 + cos(lat1) * cos(lat2) * sin(dlon/2)^2
d = 2 * R * asin(sqrt(a))
```

### Validating a flight

`validate_flight(plan, notams)` in `src/tools.py` runs these steps in order.

1. Every restrictive NOTAM that cannot be placed produces a warning that it could not be evaluated geometrically.
2. If `plan.alt` is above `max_agl_m` (120 by default), it returns a violation that cites `CAR §7`. This comes before any NOTAM, so above 120 m the citation is always `CAR §7` and never "the nearest crane".
3. For each NOTAM whose circle contains the position: an advisory is recorded and skipped, and a restrictive one with a limit that the flight exceeds is collected as a breach.
4. If there are breaches, they are sorted by lowest ceiling, then distance, then id. The first leads the reason and `notam_id`, every breached NOTAM is cited in `refs`, and the reason adds "also breaches" for the rest. The same airspace gives the same answer in any input order. The suggested fix is the ceiling minus 20 m, or "area is no-fly, reroute required" when the ceiling is zero.
5. Otherwise it returns no violation and cites `CAR §7`.

The comparisons are strict, so 120 m is legal and 121 m is not, and the same holds at 100 m and 101 m for the crane. Advisories are collected for every NOTAM in range, including those listed after a breach.

### Parsing NOTAMs

`parse_notam` in `src/core/notam_parser.py` normalises whitespace and then extracts fields with regular expressions. The identifier is `NOTAM` followed by `dd/dd`, and a line without one is not a NOTAM. The position is two decimals separated by a comma, read as latitude then longitude. The radius is `radius N km`, or failing that `N km no-fly`, with an explicit radius winning. The altitude limit is zero for a no-fly zone. Otherwise it is `max`, `maximum` or `max allowed` followed by `N m`, and failing that an obstacle's own height (`crane`, `tower`, `mast` or `obstacle` followed by `N m`). An explicit limit beats the obstacle height, which is only a proxy for it. The window is `YYYY-MM-DD to YYYY-MM-DD`, from the start of the first day to the last instant of the final day.

A NOTAM is restrictive only if it states an altitude limit. Even then, if it carries advisory wording (`caution`, `advisory`, `advised` or `reported`) and is neither a no-fly zone nor an explicit "max" limit, it is demoted to an advisory.

| NOTAM | Position | Radius | Limit | Window | Severity | Placed |
|---|---|---|---|---|---|---|
| 09/03 | 18.53, 73.84 | 1.0 km | 100 m | 2026-09-01 to 2027-12-31 | restrictive | yes |
| 09/04 | none | 5.0 km | 0 m | 2026-09-02 to 2027-12-31 | restrictive | no |
| 09/05 | 18.55, 73.86 | 2.0 km | none | none | advisory | yes |

### Grounding and lookup

```mermaid
flowchart TD
  V["validator applied CAR §7"] --> L["lookup: chunks that define each ref"]
  Q["request query"] --> S["search: similarity context"]
  L --> M["merge: defining chunks first"]
  S --> M
  M --> G{"does a chunk define the ref?"}
  G -->|"yes"| OK["grounded, excerpt starts at the definition"]
  G -->|"no"| NO["not grounded, 0.40 off confidence"]
```

`extract_refs` finds `NOTAM dd/dd` and `§N` in a piece of text, normalising the second to `CAR §N` and removing duplicates. `find_definition(ref, chunk)` is the one rule for what counts as the text of a reference. It returns the index where the reference is defined, or `None`. Grounding, the vector stores' `lookup` and the evaluation all call it.

A reference is defined where it begins the chunk, or begins a sentence inside the chunk (after `.`, `;` or `:` and a space). Leading punctuation and a byte-order mark are skipped. The reference must be a whole number, so `§7` is not satisfied by `§70`, and `09/03` is not satisfied by `09/031`.

| Chunk | Defines `CAR §7`? |
|---|---|
| `§7 Micro RPA ...` | Yes, it starts the chunk |
| `§8 Nano RPA. §7 Micro RPA ...` | Yes, and the excerpt starts at `§7` |
| `NOTAM 09/03 ... DGCA CAR §7 applies.` | No, it is a mention in the middle of a sentence |
| `§70 Something else.` | No, it is a different number |

`ground(refs, retrieved, excerpt_chars=160)` returns one `Citation` per reference, with the excerpt starting at the definition. `needle(ref)` reduces a reference to a short key (`CAR §7` becomes `§7`). It is used only to narrow a SQL query, never as proof.

### The safety policy

```
finalise(violation, citations, warnings, retrieval_failed=False,
         validated=True, cross_checked=True)

if retrieval_failed:   return HOLD, 0.0, human     (adds a retrieval warning)
if not validated:      return HOLD, 0.0, human     (adds "nothing cleared")

ungrounded  = citations that are not grounded      (adds a grounding warning)
unevaluable = len(warnings that do not mention grounding)
if not cross_checked:  add a "not cross-checked" warning

base       = 0.95 if violation else 1.00
penalty    = 0.15 * unevaluable + 0.40 * len(ungrounded)
             + (0.40 if not cross_checked else 0)
confidence = max(0.0, round(base - penalty, 2))

if violation:                                  return BLOCK, confidence, human
if not cross_checked or confidence < 0.75:     return HOLD,  confidence, human
return ALLOW, confidence, no human
```

The unevaluable count is taken before the cross-check warning is added. Otherwise that warning would be charged twice, once as unevaluable and once as unchecked.

### Tickets

Tickets exist so that two dispatchers reacting to the same restriction on the same day produce one ticket, not two.

The dedupe key is `ticket:dedupe:` followed by the first 12 hex characters of a SHA-256 over the drone id, the NOTAM id (or the first 30 characters of the issue text when there is none) and the date. The daily window means a restriction still in force tomorrow gets a new ticket, while a retry this afternoon does not. Ticket ids are `T-` and six uppercase hex characters.

In Redis, creation is a single atomic `SET key ticket_id NX EX ttl`. Exactly one caller succeeds. The others read the winner's id and return it with `deduped=True`. The winner then writes the full record under `ticket:<id>`.

```mermaid
sequenceDiagram
  participant A as Process A
  participant B as Process B
  participant R as Redis
  A->>R: SET key ticket_a NX EX 86400
  B->>R: SET key ticket_b NX EX 86400
  R-->>A: OK, A wins
  R-->>B: nil, key already set
  B->>R: GET key
  R-->>B: ticket_a
  Note over B: returns ticket_a with deduped true
  A->>R: SET ticket:ticket_a record EX 86400
```

The in-process adapter gets the same exactly-once behaviour from a `threading.Lock` around check-and-insert.

Approval is first-wins. In Redis it runs inside `transaction()`, which uses `WATCH`. It reads the record and returns it unchanged if it is already approved. Otherwise it sets `status`, `approved_by` and `approved_at` and writes with `keepttl`, so approving never makes a ticket permanent. If two approvers race, one commits and the other retries, sees `approved`, and returns the first approver.

`DynamoTicketAdapter` keeps the same two guarantees with conditional writes, which DynamoDB evaluates atomically on the item. The table has one partition key `pk` and reuses the Redis key names: `ticket:dedupe:<hash>` points at a ticket id, and `ticket:<id>` holds the ticket. Creation reads the dedupe item first, because a read is cheaper than a failed conditional write, then writes both items in one `TransactWriteItems`. The dedupe item is written only if it is absent or expired, so there is no moment when the key is taken but the ticket is not written. A ticket id is six hex digits and can collide, so the ticket item is conditional as well. A collision cancels the transaction and a new id is drawn, instead of one ticket overwriting another. Approval is one `UpdateItem` that applies only while the ticket exists, is unexpired and is not `approved`. When the condition fails, the ticket is read back: absent means unknown, anything else was already approved and is returned unchanged. `expires_at` is never written, so approving cannot make a ticket permanent. DynamoDB's TTL deletes expired items lazily, up to a couple of days late, so every read and every condition compares `expires_at` with the clock instead of trusting TTL to have run.

```mermaid
stateDiagram-v2
  [*] --> open : create, SET NX wins
  open --> open : create again, deduped
  open --> approved : approve, first caller wins
  approved --> approved : approve again, unchanged
  open --> [*] : TTL expires
  approved --> [*] : TTL expires
```

A drone's history is a Redis list: `LPUSH`, `LTRIM 0 4` and `LRANGE 0 4` in one pipeline on `drone:<id>:history`, so it holds the last five tickets, newest first.

### Retrieval

The pgvector search is one query.

```sql
SELECT chunk FROM sop_chunks ORDER BY embedding <=> %s::vector LIMIT %s
```

`<=>` is cosine distance. The embedding model (`BAAI/bge-small-en-v1.5`, 384 dimensions) and the database connection are created once per process rather than per request. On any exception the connection is dropped and `RetrievalUnavailable` is raised, and so is it when no rows come back.

The pgvector lookup narrows in SQL and then applies the exact rule in Python.

```sql
SELECT chunk FROM sop_chunks WHERE chunk ILIKE %s
```

The reference's key is bound as a parameter with LIKE wildcards escaped. The rows that come back are then filtered through `find_definition`, so a chunk that only mentions `§7` is not returned as if it were §7.

The in-memory store is a small lexical scorer. It tokenises text with `[a-z0-9§/.]+`, weights each token by `ln(1 + N / df)`, and scores a chunk as the sum of the weights of the tokens it shares with the query. It returns the top `k`. If no chunk shares any token it raises `RetrievalUnavailable`, because returning something would be a guess presented as a result. Its `lookup` applies `find_definition` to every chunk.

### Chunking

`chunk_lines` makes one chunk per non-empty line. It is the default for both the in-memory store and the ingest command, because the corpus is written one clause or one NOTAM per line and a citation refers to that unit. `chunk_words(text, size=512, overlap=50)` cuts fixed word windows and is available through `src.ingest --strategy words` for prose that is not line-structured. A window can hold several clauses, which is why the definition rule also accepts a reference at the start of a sentence.

### The router

`RuleLLMAdapter.route` returns `both` when coordinates are present and the query contains one of the whole words `notam`, `crane`, `dgca`, `car`, `rule`, `regulation` or `allowed` (singular or plural), or the `§` sign. With coordinates and no such word it returns `act`. Without coordinates it returns `retrieve`. Matching is by whole word, so `scarce`, `carry` and `cardio` do not count as `car`. `respond` returns `verdict: reason [refs]`.

`GroqLLMAdapter` wraps a `ChatGroq` model at temperature 0. To route, it sends a fixed prompt that asks for one word and looks for `both`, then `act`, then `retrieve` in the lowercased reply. Any provider error, a missing client or an unusable reply falls back to the rule adapter. To respond, it asks for one sentence that states the verdict and reason as given and quotes the references.

## 18. API

### POST /validate

| Request field | Type | Constraint |
|---|---|---|
| `lat` | float | -90 to 90 |
| `lon` | float | -180 to 180 |
| `alt` | int | 0 to 10000, metres AGL |
| `drone_id` | string | 1 to 64 characters |
| `query` | string, optional | Defaults to `validate flight against DGCA CAR and active NOTAMs` |
| `scheduled_for` | datetime, optional | UTC. NOTAM windows are evaluated at this instant. Defaults to now |

| Response field | Meaning |
|---|---|
| `verdict` | `ALLOW`, `BLOCK` or `HOLD` |
| `reason` | The operator-facing sentence. Written by the model when Groq is on |
| `confidence` | 0.0 to 1.0, built as in section 17 |
| `citations` | The references the verdict rests on |
| `evidence` | For each citation: `ref`, `grounded` and `excerpt` |
| `advisories` | Advisory NOTAMs the flight is inside |
| `warnings` | Airspace or evidence the system could not assess |
| `requires_human` | Whether a person has to act |
| `ticket_id` | Empty unless a person has to act |
| `retrieved` | The chunks retrieved, defining chunks first |
| `action` | The route taken |

An example, evaluated at an explicit time inside the sample windows:

```json
POST /validate
{"lat": 18.53, "lon": 73.84, "alt": 120, "drone_id": "D12",
 "scheduled_for": "2026-09-02T12:00:00Z"}

{
  "verdict": "BLOCK",
  "reason": "BLOCK: NOTAM 09/03: max 100m within 1.0km ... reduce to 80m",
  "confidence": 0.8,
  "citations": ["NOTAM 09/03"],
  "evidence": [{"ref": "NOTAM 09/03", "grounded": true,
                "excerpt": "NOTAM 09/03 Pune Site: Crane 100m at ..."}],
  "warnings": ["NOTAM 09/04 states a restriction but no usable ..."],
  "requires_human": true,
  "ticket_id": "T-XXXXXX",
  "action": "both"
}
```

Long strings are shortened with `...` here. The `reason` shown is the rule adapter's format. Without `scheduled_for` the same request is evaluated now, and gives the same result until the sample windows end on 2027-12-31.

### Other endpoints

| Method | Path | Purpose | Errors |
|---|---|---|---|
| GET | `/health` | Returns `ok` and `version` | none |
| POST | `/validate` | Decide one flight plan | `422` for input outside the constraints above |
| GET | `/ticket/{ticket_id}` | Ticket status, including `approved_by` | `404` if unknown |
| POST | `/approve/{ticket_id}` | Body `{"approver": ...}`, 1 to 64 characters. Closes the human gate. The first approval stands | `404` if unknown |
| GET | `/notams` | The parsed corpus, including records that could not be placed | none |
| GET | `/drone/{drone_id}/history` | The drone's recent tickets | none |

## 19. Persistence

Postgres has one table, created by `src.ingest`.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS sop_chunks (
  id        SERIAL PRIMARY KEY,
  doc_id    TEXT NOT NULL,
  chunk     TEXT NOT NULL,
  embedding vector(384)
);
CREATE INDEX IF NOT EXISTS sop_chunks_embedding_idx
  ON sop_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
```

Ingest replaces the table's contents in a single transaction. It raises on failure rather than falling back, because a service pointed at an empty table would hold every flight without saying why. `--dry-run` writes `data/chunks.json` and skips the database, and `--strategy` is `lines` (the default) or `words`.

Redis holds three kinds of key.

| Key | Value | Expiry |
|---|---|---|
| `ticket:dedupe:<12 hex>` | The winning ticket id | `TICKET_TTL_SECONDS` |
| `ticket:<ticket_id>` | The ticket as JSON | `TICKET_TTL_SECONDS`, kept on approval |
| `drone:<drone_id>:history` | The last five ticket ids | none |

## 20. Configuration

Every environment variable is read in `src/core/config.py` and nowhere else.

| Variable | Default | Purpose |
|---|---|---|
| `VECTOR_ADAPTER` | `pgvector` | `pgvector` or `memory` |
| `LLM_ADAPTER` | `groq` if `GROQ_API_KEY` is set, else `rule` | `rule` or `groq` |
| `DATABASE_URL` | `postgresql://notam:notam@localhost:5432/notam` | Postgres |
| `REDIS_URL` | `redis://localhost:6379/0` | Falls back to in-process if unreachable |
| `NOTAM_DIR` | `data/notams` | Directory the parser reads |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 384 dimensions |
| `RETRIEVAL_K` | `3` | Chunks per similarity query |
| `MAX_AGL_M` | `120` | The DGCA CAR §7 ceiling |
| `HUMAN_GATE_CONFIDENCE` | `0.75` | An `ALLOW` below this becomes a `HOLD` |
| `TICKET_TTL_SECONDS` | `86400` | Dedupe window and ticket lifetime |
| `GROQ_API_KEY`, `GROQ_MODEL` | none, `openai/gpt-oss-20b` | Optional LLM backend |
| `LANGSMITH_TRACING` or `LANGCHAIN_TRACING_V2` | `false` | Either name enables tracing |
| `LANGSMITH_API_KEY` or `LANGCHAIN_API_KEY` | none | Needed when tracing is on |
| `LOG_LEVEL` | `INFO` | |
| `REDIS_TEST_URL` | none | Tests only. Runs the Redis checks against a real server |

Two values are fixed in code: the Redis connect timeout (1 s) and the history length (5).

## 21. Errors

```
NotamGuardError
  RetrievalUnavailable      raised by the vector adapters (search and lookup)
                            caught in graph.retriever, which sets retrieval_failed
  NotamSourceUnavailable    raised by FileNotamRepository
                            caught in graph.validator, which sets validated to False
```

Infrastructure failures are typed so the graph can react to them. Nothing in the decision path catches an exception and returns an invented value.

## 22. Observability

`@traced(name)` wraps every graph node. With tracing on, a valid key and `langsmith` installed, it is `langsmith.traceable(name=..., run_type="chain")`. Otherwise it does nothing, and `langsmith` is never imported. A missing key, or one containing `...` (the placeholder in `.env.example`), switches tracing off with a single warning, instead of a `403` for every span. Each stage's time is also recorded in `state["latency_ms"]`, independently of the tracer. Logging uses the standard `logging` module at `LOG_LEVEL`, and the startup line records the vector adapter, LLM adapter and tracing state.

On the lexical path a decision takes about 3 ms in steady state. The first call takes about 3.8 s because it compiles the graph.

## 23. Web interface

The interface is a Vite, React and TypeScript app in `web/src`.

- `lib/api.ts` is a typed client for `/api/validate`, `/api/approve/{id}`, `/api/notams` and `/api/health`. It does not send `scheduled_for`.
- `lib/scenarios.ts` holds four presets that between them produce every verdict.
- `lib/verdict.ts` holds the verdict theme and `findDefinition`, which mirrors `find_definition` in `core/citations.py`, so the interface highlights where a rule is defined and not every place it is mentioned. It was checked against the Python rule on seven shared cases.
- `components/` has `Hero` (what the tool does, in plain words), `ScenarioCards`, `MapView` (a draggable pin and circles for the NOTAMs that could be placed), `HeightControl` (a slider that marks the legal limit and the ceiling of any notice the gate cited), `AdvancedOptions`, `DecisionPanel` (the answer first, then the human gate, then evidence and sources behind labelled sections), `ConfidenceMeter` (confidence drawn against the 0.75 bar), `Pipeline`, `Learn` and `DroneIcon`.
- The page re-checks the flight about 450 ms after the last change, and ignores a reply that arrives after a newer request. A plan with an invalid field is not sent. The slider's marks come from the gate's own citations, so the interface carries no second copy of the geometry.
- The verdict is shown as a plain headline (`ALLOW` is "Clear to fly", `BLOCK` is "Do not fly", `HOLD` is "Held for a person") with the gate's word beside it. The strict CSP rules out inline style attributes in markup, so the map pin is drawn with CSS classes.

The examples give the same results now, a year from now and at the evaluation instant.

| Example (id) | Verdict | Confidence | Route |
|---|---|---|---|
| Too high near a crane (`breach`) | `BLOCK` | 0.80 | both |
| A clear flight (`clear`) | `ALLOW` | 0.85 | both |
| Birds nearby (`advisory`) | `ALLOW` | 0.85 | both |
| Not enough to go on (`unchecked`) | `HOLD` | 0.45 | act |

## 24. Tests

| File | Collected | What it covers |
|---|---|---|
| `test_tools.py` | 18 | Haversine against a known distance. The boundaries at 119, 120 and 121 m, and 99, 100 and 101 m. The ceiling being checked before NOTAMs. Radius edges. Advisories never blocking, including after a breach. The most restrictive breach leading, with all breaches cited, in any order |
| `test_notam_parser.py` | 11 | A full parse. An explicit limit beating an obstacle height. A no-fly zone becoming a zero ceiling. A NOTAM without coordinates not being placed. The window including its final day. No window meaning active |
| `test_citations_and_safety.py` | 20 | Both reference styles. A mention not grounding a rule. `§70` not grounding `§7`. A mid-chunk clause grounding with the excerpt at the clause. A byte-order mark being ignored. An unvalidated plan holding. Nothing retrieved holding, whatever the gate is set to. Penalties not being counted twice. A `BLOCK` never being downgraded |
| `test_graph.py` | 21 | The router really branching. A dead store holding. An irrelevant retriever holding. A misrouted request held at any altitude. The `act` route holding with no other warning. An unreadable NOTAM source holding. Cited rules fetched by name, and a lookup failure holding. The validator running before the retriever. One ticket for repeated requests |
| `test_lookup.py` | 9 | Lookup returning the defining chunk and not a mention, for both adapters. The SQL being parameterised with wildcards escaped. A database error being a retrieval failure |
| `test_redis_adapters.py` | 10 | Fifty concurrent creates through separate clients giving one ticket. Expiry on tickets and dedupe keys. The first approval standing, under concurrency. History keeping five, newest first. An unreachable Redis giving no client. One optional test against a real Redis |
| `test_ticket_idempotency.py` | 7 | The same fifty-way check for the in-process adapter. Different drones or NOTAMs getting different tickets. The window rolling over at midnight |
| `test_ingest.py` | 6 | One chunk per line giving 8 chunks. Ingest and the in-memory store agreeing. No byte-order marks. An unknown strategy being rejected |
| `test_llm_router.py` | 9 | Regulatory wording routing to `both`. `scarce`, `carry` and `cardio` not doing so |
| `test_sample_data.py` | 2 | The sample windows having at least 60 days left. The evaluation instant being inside them |
| `test_api.py` | 14 | The shape of `/validate`, input validation, the ticket lifecycle through approval, the `404`s, and `scheduled_for` changing the outcome |

`conftest.py` sets `VECTOR_ADAPTER=memory` and `LLM_ADAPTER=rule`, resets settings and the container around each test, and pins time to 2026-09-02 at 12:00 UTC. Its `wired` fixture injects in-memory adapters over a fixed airspace: a crane, a runway that cannot be placed, and a bird advisory.

No test touches `PgVectorAdapter.search` against a real database, `GroqLLMAdapter` against a real provider, or a live Redis (unless `REDIS_TEST_URL` is set).

## 25. Evaluation harness

`src/eval.py` scores `data/test_queries.json` at a fixed instant, 2026-09-02 at 12:00 UTC, so the result does not depend on the date it is run. It exits non-zero if a verdict or a route is wrong.

Routing accuracy is the share of cases whose route matches the expected one. Verdict accuracy is the share whose verdict matches. Retrieval hit rate is the share of cited cases in which similarity search alone puts the chunk that defines the expected reference in the top `k`. The graph's lookup is left out of this on purpose, so the number reflects the retriever. Grounded citation rate is the share of cited cases in which every citation is grounded after the full graph, which includes the lookup. For a decision with no citations it is vacuously true. The report also gives the count of `HOLD` verdicts (2) and the median and 95th-percentile latency, where the 95th includes the first call's graph compilation.

The current result is 16 cases, routing 1.0, verdict 1.0, retrieval 0.857, grounding 1.0, and 2 held.

The golden set covers both sides of each threshold (119, 120 and 121 m, and 99, 100 and 101 m), the radius edges (0.15 km inside, 1.53 km outside, 5.4 km away), citation precedence above 120 m, advisory handling and the `act` route.

## 26. Running it

```bash
git clone https://github.com/maczeo11/notam-guard && cd notam-guard
python -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

VECTOR_ADAPTER=memory LLM_ADAPTER=rule python -m pytest    # 126 passed, 1 skipped
VECTOR_ADAPTER=memory LLM_ADAPTER=rule python src/eval.py  # the 16-case golden set
VECTOR_ADAPTER=memory LLM_ADAPTER=rule uvicorn src.app:app --port 8000
```

To run the Redis checks against a real server:

```bash
REDIS_TEST_URL=redis://localhost:6379/1 \
  python -m pytest tests/test_redis_adapters.py
```
