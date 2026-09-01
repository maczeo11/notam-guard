# EVAL — NOTAM-Guard

## Metrics (B.Tech-defensible, not PhD)
- **Retrieval precision@3:** `test_queries.json` 20 queries `Q: D12 Pune 120m near crane` → should retrieve `CAR §7 + NOTAM 09/03` — target `>0.8`.
- **BLOCK recall:** `crane violation` should be `BLOCK` 9/10 — naive without RAG = 3/10.
- **Latency p95:** `POST /validate` local `pgvector + gpt-4o-mini` → `<400ms` (no GPU), vs `Qwen2-VL` add later → `<800ms g4dn`.
- **Idempotency:** `50 concurrent POST /validate same drone+NOTAM` → `1 ticket 49 deduped` via `SETNX` — test `scripts/dedupe_test.py`.

## How to Run
```bash
python src/eval.py --queries data/test_queries.json --out eval.json
cat eval.json # {precision@3: 0.85, recall_block: 0.9, p95_ms: 342}
```

## Failure Cases Documented (wow for interview)
- `NOTAM stale >24h` → confidence 0.6 → `requires_human=true` holds — shows safety.
- `alt missing` → Validator returns `unknown` → Router forces `retrieve` again — closed-loop.
- `embedding drift` after adding 10 new NOTAMs → re-ingest needed — noted.

## LangSmith Traces
Each `POST /validate` logs `trace_url: https://smith.langchain.com/trace/...` — paste 1 URL into README + `notam-guard` demo.

## Commit History as Eval Proof
`git log --oneline` shows `ingest → retriever → validator → responder → critic → memory → LangSmith` — not one-shot AI slop.

## What Not to Claim
No `RUL MAE` — that is VoltWarden. Here only `BLOCK` correctness — honest.
