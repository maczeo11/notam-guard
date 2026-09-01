"""Vector stores.

Both adapters fail closed: if the corpus cannot be searched they raise
`RetrievalUnavailable` rather than returning placeholder text. The previous
version caught every exception and returned two hardcoded chunks, which meant a
dead database still produced a confident ALLOW with fabricated citations.
"""
from typing import List
import logging
import math
import re

from src.core.chunking import chunk_lines
from src.core.config import REPO_ROOT, get_settings
from src.core.errors import RetrievalUnavailable
from src.core.ports import VectorStorePort

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9§/.]+")


class PgVectorAdapter(VectorStorePort):
    """pgvector similarity search. The embedding model and connection are loaded
    once per process — the previous version re-loaded SentenceTransformer on
    every request, which dominated latency."""

    def __init__(self):
        self._model = None
        self._conn = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(get_settings().embedding_model)
        return self._model

    def _get_conn(self):
        import psycopg2
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(get_settings().database_url)
        return self._conn

    def search(self, query: str, k: int = 3) -> List[str]:
        try:
            embedding = self._get_model().encode(query).tolist()
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chunk FROM sop_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
                    (embedding, k))
                rows = [r[0] for r in cur.fetchall()]
        except Exception as exc:
            self._conn = None
            log.error("vector search failed: %s", exc)
            raise RetrievalUnavailable(str(exc)) from exc
        if not rows:
            raise RetrievalUnavailable("vector store returned no chunks — corpus not ingested?")
        return rows


class InMemoryVectorAdapter(VectorStorePort):
    """Lexical fallback over the same corpus files, so the pipeline and the eval
    can run without Postgres. Scoring is IDF-weighted token overlap: crude next to
    embeddings, but it genuinely varies with the query, so retrieval quality is
    measured rather than assumed."""

    def __init__(self, corpus: List[str] | None = None):
        self._chunks = corpus if corpus is not None else self._load_corpus()
        if not self._chunks:
            raise RetrievalUnavailable("in-memory corpus is empty")
        self._tokenised = [set(_TOKEN.findall(c.lower())) for c in self._chunks]
        self._idf = self._build_idf()

    @staticmethod
    def _load_corpus() -> List[str]:
        settings = get_settings()
        chunks: List[str] = []
        car = REPO_ROOT / "data" / "dgca_car.txt"
        if car.is_file():
            chunks.extend(chunk_lines(car.read_text(encoding="utf-8")))
        if settings.notam_dir.is_dir():
            for path in sorted(settings.notam_dir.glob("*.txt")):
                chunks.extend(chunk_lines(path.read_text(encoding="utf-8")))
        return chunks

    def _build_idf(self) -> dict:
        n = len(self._tokenised)
        counts: dict[str, int] = {}
        for tokens in self._tokenised:
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
        return {token: math.log(1 + n / count) for token, count in counts.items()}

    def search(self, query: str, k: int = 3) -> List[str]:
        query_tokens = set(_TOKEN.findall(query.lower()))
        scored = []
        for chunk, tokens in zip(self._chunks, self._tokenised):
            score = sum(self._idf.get(t, 0.0) for t in query_tokens & tokens)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if not scored:
            # No lexical overlap at all. Returning the whole corpus head would be
            # a guess dressed as a result, so treat it as a retrieval miss.
            raise RetrievalUnavailable(f"no chunk matched query: {query!r}")
        return [chunk for _, chunk in scored[:k]]
