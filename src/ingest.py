"""Ingest the regulatory corpus into pgvector.

Run: python -m src.ingest --docs "data/dgca_car.txt" "data/notams/*.txt"
"""
from pathlib import Path
from typing import List
import argparse
import glob
import json
import logging
import sys

from src.core.chunking import chunk_words
from src.core.config import REPO_ROOT, get_settings

log = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS sop_chunks (
    id        SERIAL PRIMARY KEY,
    doc_id    TEXT NOT NULL,
    chunk     TEXT NOT NULL,
    embedding vector(384)
);
CREATE INDEX IF NOT EXISTS sop_chunks_embedding_idx
    ON sop_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
"""


def collect_chunks(patterns: List[str], chunk_size: int, overlap: int) -> List[dict]:
    chunks: List[dict] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if not matches:
            log.warning("no files matched %s", pattern)
        for path in matches:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            for chunk in chunk_words(text, chunk_size, overlap):
                chunks.append({"doc_id": path, "chunk": chunk})
    return chunks


def write_to_pgvector(chunks: List[dict]) -> int:
    """Embed and upsert. Raises on failure — a silent fallback would leave the
    service querying an empty table and reporting HOLD for every flight."""
    import psycopg2
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    model = SentenceTransformer(settings.embedding_model)
    embeddings = model.encode([c["chunk"] for c in chunks]).tolist()

    with psycopg2.connect(settings.database_url) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.execute("DELETE FROM sop_chunks;")
            cur.executemany(
                "INSERT INTO sop_chunks (doc_id, chunk, embedding) VALUES (%s, %s, %s)",
                [(c["doc_id"], c["chunk"], e) for c, e in zip(chunks, embeddings)])
        conn.commit()
    return len(chunks)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingest corpus into pgvector")
    parser.add_argument("--docs", nargs="+", required=True, help="file globs")
    parser.add_argument("--chunk", type=int, default=512, help="chunk size in words")
    parser.add_argument("--overlap", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true",
                        help="write data/chunks.json instead of touching the database")
    args = parser.parse_args(argv)

    chunks = collect_chunks(args.docs, args.chunk, args.overlap)
    if not chunks:
        log.error("nothing to ingest")
        return 1
    log.info("collected %d chunks", len(chunks))

    if args.dry_run:
        out = REPO_ROOT / "data" / "chunks.json"
        out.write_text(json.dumps(chunks, indent=2), encoding="utf-8")
        log.info("dry run — wrote %s", out)
        return 0

    try:
        count = write_to_pgvector(chunks)
    except Exception as exc:
        log.error("ingest failed: %s", exc)
        log.error("start the database with `docker compose up -d postgres`, "
                  "or re-run with --dry-run")
        return 1
    log.info("inserted %d chunks into pgvector", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
