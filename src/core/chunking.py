"""Text chunking shared by the ingest CLI and the in-memory vector store."""
from typing import List


def chunk_words(text: str, size: int = 512, overlap: int = 50) -> List[str]:
    """Fixed-width word windows with overlap, for the pgvector ingest path."""
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be in [0, size)")
    words = text.split()
    if not words:
        return []
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + size]))
        i += size - overlap
    return chunks


def chunk_lines(text: str) -> List[str]:
    """One chunk per non-empty line.

    The corpus here is line-delimited by construction — one DGCA clause or one
    NOTAM per line — so this preserves the unit a citation refers to.
    """
    return [line.strip() for line in text.splitlines() if line.strip()]
