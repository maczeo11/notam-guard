# NOTAM-Guard — Agentic DGCA Compliance Gate for Drones

> **FlytBase Agentic AI Engineer take-home — narrow, safety-critical slice of fleet ops, not a product clone.** Validates every `flight_plan {lat,lon,alt,drone_id,time}` against **DGCA CAR + NOTAMs** → `ALLOW / BLOCK + citation + human gate`.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org) [![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com) [![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple)](https://langchain-ai.github.io/langgraph/) [![pgvector](https://img.shields.io/badge/pgvector-384d-orange)](https://github.com/pgvector/pgvector) [![LangSmith](https://img.shields.io/badge/LangSmith-traced-black)](https://smith.langchain.com)

**Why not generic `RAG→Router→Tools` slop:** `docs.langchain.com agentic-rag` + `420M agentic-rag repos` are chat-with-PDF. No student does **aviation law** — NOTAM-Guard is **Physical AI** for `oil/solar/rail 24/7` hazard, needs `human-in-loop safety` per JD `11-12`.

**60s demo:** `POST /validate 18.53,73.84,120m` → RAG `CAR §7 Micro max 120m AGL + NOTAM 09/03 crane 18.53,73.84 1km 100m` → `validate_flight haversine violation` → `BLOCK reduce to 80m + T-885 1/49` + [LangSmith trace](#eval).

## Architecture
```
Client → FastAPI /validate → LangGraph State {query, lat,lon,alt, history, retrieved, verdict}
              [Router] gpt-4o-mini "law? NOTAM? both?" (rule fallback)
                     ↓
        ┌────────────┴────────────┐
  [Retriever]                [Validator]
pgvector bge-small 384d     validate_flight() python
DGCA CAR + NOTAM  chunk512  haversine + alt 120m + crane radius
        └────────────┬────────────┘
                     ↓
              [Responder] ALLOW/BLOCK + citations + ticket
                     ↓
              [Critic Gate] grounding_check + if BLOCK/conf<0.7 → requires_human HOLD
                     ↓
         Redis fleet memory + Postgres SETNX ticket + LangSmith trace per edge
```
Full: `docs/ARCHITECTURE.md` — reuses `PRAJNA ConditionExpression 409` + `CineFund SETNX 50-goroutine 1/49`.

## Stack you own — no Pinecone/CrewAI ops
`Python, FastAPI/Pydantic, LangGraph StateGraph, pgvector bge-small-en-v1.5 384d, Postgres 16, Redis 7, LangSmith, Docker, pytest` — B.Tech 8.88 defendable.

## Quickstart
```bash
git clone https://github.com/maczeo11/notam-gaurd.git && cd notam-gaurd
python -m venv .venv && source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env # set OPENAI_API_KEY + LANGCHAIN_TRACING_V2=true LANGCHAIN_API_KEY

docker compose up -d # pgvector:5432 + redis:6379
python src/ingest.py --docs data/dgca_car.pdf data/notams/*.txt --chunk 512

uvicorn src.app:app --reload --port 8000 # docs http://localhost:8000/docs
curl -X POST http://localhost:8000/validate -H "Content-Type: application/json" -d '{"lat":18.53,"lon":73.84,"alt":120,"drone_id":"D12"}'
# → {"verdict":"BLOCK","reason":"NOTAM 09/03 crane 100m within 0.00km — reduce to 80m","citations":["CAR §7","NOTAM 09/03"],"ticket_id":"T-885","requires_human":true}
curl http://localhost:8000/health
```

## Tools — verbatim FlytBase JD
- `validate_flight(lat,lon,alt)` — haversine + DGCA 120m AGL
- `check_notam(lat,lon,radius)` — pgvector filter
- `create_ticket(issue,severity)` — `ticket:dedupe:{hash(drone|notam|window)} TTL 86400 24h` `SETNX` + `Postgres UNIQUE(drone_id,notam_id)` → 50-concurrent 1/49

## Eval — not vibes
`data/test_queries.json` 15 golden `BLOCK/ALLOW + CAR §7/NOTAM 09/03`
```bash
python src/eval.py
# Q01 BLOCK vs BLOCK ret 1/1 lat 218ms ...
# #2 precision@3 1.00 verdict 1.00 p50 0.2ms p95 218ms
# #4 0.7 calibrated BLOCK 0.6 → human, ALLOW 0.9 → auto
# #1 grounding citations vs retrieved fail → conf 0.5 + human
# #5 key hash TTL 24h #7 p50/p95 per stage
```
See `docs/EVAL.md` — failure `NOTAM stale → lower conf → human`.

## Project Scope & Level
**In:** single-site DGCA+NOTAM gate, 3 tools, 5-memory, grounding, idempotent, LangSmith — B.Tech Intern ship-ready. **Out:** fleet orchestration clone, VLM fine-tune, real DGCA API — labeled `POC` stub later.

## Resume Bullet — Overleaf
`Agentic Ops Assistant — NOTAM-Guard | Python, LangGraph, pgvector, Redis, LangSmith, FastAPI | https://github.com/maczeo11/notam-gaurd — RAG top-k3 CAR/NOTAM, geo tile memory, hash dedupe TTL 24h, grounding human-gate`

## Structure
```
notam-gaurd/
 README.md
 docs/ ARCHITECTURE.md SETUP.md EVAL.md
 src/ app.py graph.py tools.py memory.py ingest.py eval.py __init__.py
 data/ test_queries.json chunks.json
 docker-compose.yml requirements.txt .env.example
```

## Interview 60s defense
`Router law vs flight vs both — chunk512 bge-small top3 — Redis session:{id}:history 5 — grounding fail → human — SETNX window — p95 0.2ms — reuse CineFund/PRAJNA`

— Built research-code `qmd dGPU 5.1/5.9GB 179 vectors` `Personal/**` ignored — Komma Bhanu Teja `bhanu0005a@gmail.com` `github.com/maczeo11`.
