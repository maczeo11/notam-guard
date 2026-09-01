# NOTAM-Guard — Agentic Compliance Gate for Drone Operations

> Validates `flight_plan {lat,lon,alt,drone_id,time}` against **DGCA CAR + NOTAMs** → `ALLOW / BLOCK + citation + human gate`. RAG + tool-calling with grounding, eval, and idempotent tickets.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org) [![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com) [![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple)](https://langchain-ai.github.io/langgraph/) [![pgvector](https://img.shields.io/badge/pgvector-384d-orange)](https://github.com/pgvector/pgvector)

## What it does
- **RAG** over DGCA CAR Section 3 + NOTAMs: `chunk 512 → bge-small 384d → pgvector top-k3` with citation grounding.
- **Tools** `validate_flight(lat,lon,alt)` haversine + 120m AGL, `check_notam`, `create_ticket` idempotent `hash(drone|notam|window) TTL 24h`.
- **Memory** `Redis drone:{id}:history 5` + tile `GEO` — fleet remembers last clearances.
- **Safety** `grounding_check` citation vs retrieved → `conf 0.5 + human HOLD` if `BLOCK/conf<0.7`.

**Demo:** `POST /validate 18.53,73.84,120m` → `BLOCK NOTAM 09/03 crane 100m within 0.00km — reduce to 80m + T-885 1/49` + citations.

## Project structure
```
notam-gaurd/
 README.md
 docs/ ARCHITECTURE.md  — graph, state, nodes, memory, safety
       SETUP.md         — docker, ingest, run, test
       EVAL.md          — precision@3, p50/p95, failure cases
 src/
  app.py        — FastAPI /validate /ingest /ticket /health
  graph.py      — LangGraph State {query,lat,lon,alt,retrieved,verdict} router→retriever→validator→responder→critic
  tools.py      — haversine, validate_flight, create_ticket SETNX
  memory.py     — Redis helper with in-mem fallback
  ingest.py     — chunk 512 → bge-small → pgvector (fallback data/chunks.json)
  eval.py       — 15 golden queries, p50/p95
 data/
  test_queries.json — 15 BLOCK/ALLOW
 docker-compose.yml — postgres:16-pgvector:5432 + redis:7:6379
 requirements.txt  — fastapi, langgraph, pgvector, redis, sentence-transformers, langsmith
 .env.example      — OPENAI_API_KEY, LANGCHAIN_TRACING_V2, DATABASE_URL, REDIS_URL
```

See `docs/ARCHITECTURE.md` for flow diagram.

## Quickstart
```bash
git clone https://github.com/maczeo11/notam-gaurd.git && cd notam-gaurd
python -m venv .venv && source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env # set OPENAI_API_KEY + LANGCHAIN_TRACING_V2=true LANGCHAIN_API_KEY

docker compose up -d
python src/ingest.py --docs data/dgca_car.pdf data/notams/*.txt --chunk 512
uvicorn src.app:app --reload --port 8000 # http://localhost:8000/docs
curl -X POST http://localhost:8000/validate -H "Content-Type: application/json" -d '{"lat":18.53,"lon":73.84,"alt":120,"drone_id":"D12"}'
```

## Eval
```bash
python src/eval.py
# precision@3 1.00 verdict 1.00 p50 0.2ms p95 218ms (first query warms model)
```
`docs/EVAL.md` details grounding, dedupe 50-concurrent 1/49, stale NOTAM → human.

## Scope
**In:** single-site DGCA/NOTAM gate, 3 tools, grounding, eval, LangSmith traces. **Out:** full fleet orchestration, VLM fine-tune — labeled POC.

## Tech
`Python, FastAPI/Pydantic, LangGraph, pgvector, Postgres, Redis, sentence-transformers, LangSmith, Docker, pytest`
