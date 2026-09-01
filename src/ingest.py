import os, glob, argparse
from pathlib import Path

# Reuse extractor pipeline if available: magic-byte + chunk 512 -> bge-small -> pgvector
# Mock for now — writes to data/chunks.json if DB not up

def chunk_text(text, size=512, overlap=50):
    words = text.split()
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i+size]))
        i += size - overlap
    return out

def ingest(paths, chunk_size=512):
    chunks = []
    for pat in paths:
        for fp in glob.glob(pat):
            txt = Path(fp).read_text(encoding="utf-8", errors="ignore")[:20000]
            # magic-byte check placeholder — real uses extractor buffer
            for c in chunk_text(txt, chunk_size):
                chunks.append({"doc_id": fp, "chunk": c})
    print(f"Ingested {len(paths)} patterns → {len(chunks)} chunks")
    # try pgvector insert — fallback json
    try:
        import psycopg2
        from pgvector.psycopg2 import register_vector
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        conn = psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://notam:notam@localhost:5432/notam"))
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("CREATE TABLE IF NOT EXISTS sop_chunks (id SERIAL PRIMARY KEY, doc_id TEXT, chunk TEXT, embedding vector(384));")
        cur.execute("DELETE FROM sop_chunks;")
        for ch in chunks:
            emb = model.encode(ch["chunk"]).tolist()
            cur.execute("INSERT INTO sop_chunks (doc_id, chunk, embedding) VALUES (%s,%s,%s)", (ch["doc_id"], ch["chunk"], emb))
        print(f"Inserted {len(chunks)} into pgvector")
    except Exception as e:
        print(f"DB not ready ({e}) — wrote data/chunks.json")
        Path("data/chunks.json").parent.mkdir(exist_ok=True)
        import json
        Path("data/chunks.json").write_text(json.dumps(chunks[:100], indent=2))
    return chunks

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="+", required=True)
    ap.add_argument("--chunk", type=int, default=512)
    args = ap.parse_args()
    ingest(args.docs, args.chunk)
