# SETUP — NOTAM-Guard

## Prereqs
- Python 3.11, Docker Desktop, Git, `LANGCHAIN_API_KEY` for LangSmith (free tier)
- Victus 16GB — runs without GPU

## 1. Clone & Env
```bash
git clone https://github.com/maczeo11/notam-guard && cd notam-guard
python -m venv .venv && source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env # set OPENAI_API_KEY, LANGCHAIN_TRACING_V2=true, LANGCHAIN_API_KEY
```

## 2. Infra
```bash
docker compose up -d # postgres:16-pgvector on 5432, redis:7 on 6379
# check: docker ps
```

## 3. Ingest DGCA + NOTAMs
Place `data/dgca_car.pdf` (DGCA CAR Section 3 Air Transport) + `data/notams/*.txt` (10 sample NOTAMs e.g., `notam_0903_crane.txt`)
```bash
python src/ingest.py --docs data/dgca_car.pdf data/notams/*.txt --chunk 512 --model BAAI/bge-small-en-v1.5
# verifies: 30 chunks → pgvector
```

## 4. Run API
```bash
uvicorn src.app:app --reload --port 8000
# docs: http://localhost:8000/docs
```

## 5. Test
```bash
curl -X POST http://localhost:8000/validate -H "Content-Type: application/json" -d '{"lat":18.52,"lon":73.85,"alt":120,"drone_id":"D12"}'
# expect: {"verdict":"BLOCK","reason":"crane NOTAM 09/03 1km + DGCA 120m","ticket_id":"T-885","citations":["CAR §7","NOTAM 09/03"],"requires_human":true}
curl -X POST http://localhost:8000/approve/T-885 # human gate
```

## 6. LangSmith
Set in `.env` then each request shows trace URL in logs/ `docs/EVAL.md`.

## 7. Eval
```bash
python src/eval.py --queries data/test_queries.json # precision@3, p95
```

## Troubleshooting
- `qmd` not indexed `Personal/**` — correct, never put NOTAM data there.
- `psycopg2` fail → `pip install psycopg2-binary`
- `bge-small` download ~80MB first run.

## Next: Push 15 commits
```bash
git add ingest.py && git commit -m "ingest: chunk512 bge pgvector"
# ... per node
```
