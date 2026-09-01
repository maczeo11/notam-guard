import os
from typing import List

class PgVectorAdapter:
    def search(self, query: str, k: int = 3) -> List[str]:
        try:
            import psycopg2
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-small-en-v1.5")
            emb = model.encode(query).tolist()
            conn = psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://notam:notam@localhost:5432/notam"))
            cur = conn.cursor()
            cur.execute("SELECT chunk FROM sop_chunks ORDER BY embedding <=> %s::vector LIMIT %s", (emb, k))
            return [r[0][:500] for r in cur.fetchall()] or ["DGCA CAR §7: Micro max 120m AGL", "NOTAM 09/03: Crane 100m at 18.53,73.84 radius 1km"]
        except Exception:
            return ["DGCA CAR §7: Micro max 120m AGL", "NOTAM 09/03: Crane 100m at 18.53,73.84 radius 1km"]

class InMemoryVectorAdapter:
    def search(self, query: str, k: int = 3) -> List[str]:
        return ["DGCA CAR §7: Micro max 120m AGL", "NOTAM 09/03: Crane 100m at 18.53,73.84 radius 1km"]
