# NOTAM-Guard Architecture — Deep Dive

## Goal
Block unsafe drone dispatch before fleet orchestration. Narrow, safety-critical, defensible for B.Tech 8.88 — not fleet clone.

## Components
1. **Ingest `src/ingest.py`:** `DGCA CAR.pdf` + `NOTAM txt` → Universal Text Extractor magic-byte → chunk 512 tokens overlap 50 → `bge-small-en 384d` → `pgvector` table `sop_chunks(id, doc_id, chunk, embedding vector(384), meta jsonb)` — reuse `Personal/Resume/...:48`.
2. **State `src/graph.py`:** `TypedDict State {query, lat,lon,alt, drone_id, history: list, retrieved: list[chunk], verdict: ALLOW|BLOCK, confidence: float, citations: list, ticket_id}` — LangGraph `StateGraph` 4 nodes.
3. **Nodes:**
   - **Router LLM `gpt-4o-mini` temp 0:** Prompt `Decide: retrieve if asks law/NOTAM, act if flight plan with coords, both if coords + conflict. Output JSON {action: "retrieve|act|both"}` — your multi-agent claim, not fixed pipeline.
   - **Retriever:** `pgvector` `SELECT chunk FROM sop_chunks ORDER BY embedding <=> $1 LIMIT 3` — returns `CAR §7` + `NOTAM 09/03 crane`.
   - **Validator `src/tools.py`:** `validate_flight(lat,lon,alt)` — `haversine(lat,lon, crane_lat, crane_lon) <1km and alt>100 → violation` + `DGCA 120m AGL` check. Pure Python, testable, no LLM hallucination.
   - **Responder LLM:** Prompt `Synthesize verdict using retrieved + validator output, cite § and NOTAM id, if violation propose alt 80m`.
   - **Critic Gate:** `if verdict==BLOCK or confidence<0.7 or action==shutdown → requires_human=true` — hold queue `PRAJNA 409` style, human approves via `POST /approve/{ticket_id}`.
4. **Memory `src/memory.py`:** `Redis` `LPUSH drone:{id}:history ticket_id` `LTRIM 0 4` + `GEOADD fleet:tiles lon lat drone_id` — remembers per-tile last 5 clearances, prevents duplicate `SETNX ticket:dedupe:{drone_id}:{notam_id}` → `Postgres UNIQUE`.
5. **API `src/app.py` FastAPI:** `POST /validate`, `POST /ingest`, `GET /ticket/{id}`, `POST /approve/{id}` — `Pydantic` `FlightPlan(lat: float, lon: float, alt: int, drone_id: str)` — `Uvicorn` async.
6. **Observability:** `LangSmith @traceable` wraps each node — trace URL per request logged — JD `observability tools such as LangSmith`.
7. **Deploy:** `Docker compose: postgres:16-pgvector, redis:7` → `AWS ECS Fargate` or `g4dn` if add VLM later — `p95 <400ms` measured, no GPU needed for RAG.

## Data Flow Example
`D12 18.52,73.85,120m` → Router `both` → Retriever `CAR §7 + NOTAM crane 18.53,73.84 1km` → Validator `violation` → Responder `BLOCK reduce to 80m + citation` → Critic `hold` → `T-885 1/49` → `Redis` save.

## Why Not Slop
Closed-loop: `validate → retrieve → ticket` not one-shot chat. Shows `autonomous execution of Python functions/APIs` verbatim + `persistent memory` per fleet tile + `human-in-loop safety`.

## Failure Modes Handled
- `NOTAM stale >24h` → Critic lowers confidence → human.
- `embedding drift` → eval `precision@3` in `EVAL.md` monitors.
- `duplicate dispatch` → `SETNX` 1 credit.

## Extensions (post-shortlist)
Add `VLM Qwen2-VL-2B` `Perceiver` for thermal image before Router → `FlareSentry` — hits VLM bullet without overclaiming now.
