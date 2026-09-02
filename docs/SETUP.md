# Setup

## Prerequisites

Python 3.11+. Docker is optional — the service runs without Postgres, Redis or an
LLM provider by selecting the in-process adapters.

## Fastest path: no infrastructure

```bash
git clone https://github.com/maczeo11/notam-guard && cd notam-guard
python -m venv .venv && .venv/Scripts/activate    # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

VECTOR_ADAPTER=memory LLM_ADAPTER=rule python -m pytest
VECTOR_ADAPTER=memory LLM_ADAPTER=rule uvicorn src.app:app --reload --port 8000
```

This uses lexical retrieval over `data/`, the deterministic router, and in-process
memory and tickets. Verdict logic is identical to the full stack — only the retrieval
backend and the sentence rendering differ.

## Full stack

```bash
docker compose up -d                 # pgvector on 5432, redis on 6379, api, web
python -m src.ingest --docs "data/dgca_car.txt" "data/notams/*.txt"
```

`ingest` embeds with `bge-small-en-v1.5` (~80MB on first run) and writes to
`sop_chunks`. It raises on failure rather than falling back, because a service
pointed at an empty table would `HOLD` every flight without saying why. Use
`--dry-run` to write `data/chunks.json` and skip the database.

Then `http://localhost:8000/docs` for the API, `http://localhost:5173` for the map UI.

## Configuration

Every variable is read in `src/core/config.py` and nowhere else.

| Variable | Default | Purpose |
|---|---|---|
| `VECTOR_ADAPTER` | `pgvector` | `pgvector` or `memory` |
| `LLM_ADAPTER` | `groq` if `GROQ_API_KEY` else `rule` | `rule`, `groq`, `ollama` |
| `DATABASE_URL` | `postgresql://notam:notam@localhost:5432/notam` | |
| `REDIS_URL` | `redis://localhost:6379/0` | degrades to in-process if unreachable |
| `NOTAM_DIR` | `data/notams` | corpus the parser reads |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 384-dimensional |
| `RETRIEVAL_K` | `3` | chunks per query |
| `MAX_AGL_M` | `120` | DGCA CAR §7 ceiling |
| `HUMAN_GATE_CONFIDENCE` | `0.75` | below this an `ALLOW` becomes a `HOLD` |
| `TICKET_TTL_SECONDS` | `86400` | dedupe window |
| `GROQ_API_KEY` | — | optional |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | see the note below before changing |
| `LANGSMITH_TRACING` / `LANGCHAIN_TRACING_V2` | `false` | either name enables LangSmith spans |
| `LANGSMITH_API_KEY` / `LANGCHAIN_API_KEY` | — | required when tracing is on |
| `LOG_LEVEL` | `INFO` | |

No key is required to run the service or the tests.

### A note on the Groq model

The default is `openai/gpt-oss-20b` because the Llama models are no longer
reachable on a standard key: `llama-3.1-8b-instant` and `llama-3.3-70b-versatile`
return `404 — does not exist or you do not have access to it` (Enterprise tier),
and `gemma2-9b-it`, `llama3-8b-8192` and `llama-3.1-70b-versatile` return `400 —
decommissioned`. If your key reaches a different model, set `GROQ_MODEL`.

The verdict does not depend on this. With the model unreachable the router and
responder fall through to `RuleLLMAdapter`, and the decision is unchanged — only
the wording of the sentence differs.

## Tracing

LangSmith renamed its environment variables. Both forms work here; the
`LANGSMITH_*` names are current, the `LANGCHAIN_*` names are the legacy form.

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_pt_...      # smith.langchain.com → Settings → API Keys
export LANGSMITH_PROJECT=notam-guard
```

Each graph node is decorated with `@traced`, so a trace shows which branch the
router took and where the time went. With tracing off the decorator is a no-op
and `langsmith` is never imported.

If the key is missing or still holds the `lsv2_...` placeholder from
`.env.example`, tracing is disabled with a single warning rather than letting
every span fail with a `403`.

## Trying the human gate

```bash
# A flight above the crane's 100m ceiling — blocked and held.
curl -X POST http://localhost:8000/validate -H "Content-Type: application/json" \
  -d '{"lat":18.53,"lon":73.84,"alt":120,"drone_id":"D12"}'

curl http://localhost:8000/ticket/T-XXXXXX
curl -X POST http://localhost:8000/approve/T-XXXXXX \
  -H "Content-Type: application/json" -d '{"approver":"ops@example.com"}'
```

Repeat the `validate` call — the same ticket id comes back rather than a second
ticket, for 24 hours.

To see a decision change with time, pass `scheduled_for`. NOTAM 09/03 expires
2026-09-10, so the same plan is `BLOCK` before it and `ALLOW` after:

```bash
curl -X POST http://localhost:8000/validate -H "Content-Type: application/json" \
  -d '{"lat":18.53,"lon":73.84,"alt":120,"drone_id":"D12","scheduled_for":"2026-09-15T12:00:00Z"}'
```

## Adding NOTAMs

Drop a `.txt` file in `data/notams/`, one record per line. `GET /notams` shows what
the parser extracted, including `geolocatable: false` for records it could not place —
those are reported on every decision and reduce confidence rather than being ignored.
Re-run `src.ingest` so retrieval sees the new text too.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Every flight returns `HOLD` with "retrieval unavailable" | Postgres is down or the corpus was never ingested. This is the intended fail-closed behaviour. |
| `RetrievalUnavailable: vector store returned no chunks` | Run `python -m src.ingest`. |
| `Redis unavailable … using in-process memory` | Expected without Docker; tickets and history become process-local. |
| Confidence is 0.85 instead of 1.0 on a clear flight | NOTAM 09/04 has no coordinates and cannot be evaluated. Working as designed. |
| `ModuleNotFoundError: langgraph` | The sequential fallback runs instead; install it for the real state machine. |
