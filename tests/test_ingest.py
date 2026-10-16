"""Ingest chunking: the pgvector path must see the same corpus as the in-memory path."""
import pytest

from src.adapters.pgvector_adapter import InMemoryVectorAdapter
from src.core.config import REPO_ROOT
from src.ingest import collect_chunks

DOCS = [str(REPO_ROOT / "data" / "dgca_car.txt"), str(REPO_ROOT / "data" / "notams" / "*.txt")]


def test_line_chunking_gives_one_chunk_per_clause_and_record():
    chunks = [c["chunk"] for c in collect_chunks(DOCS, 512, 50, strategy="lines")]
    assert len(chunks) == 8   # title line + 4 clauses + 3 NOTAMs
    assert any(c.startswith("§7 Micro RPA") for c in chunks)
    assert any(c.startswith("NOTAM 09/03") for c in chunks)


def test_the_ingest_and_in_memory_paths_see_the_same_chunks():
    ingested = sorted(c["chunk"] for c in collect_chunks(DOCS, 512, 50, strategy="lines"))
    in_memory = sorted(InMemoryVectorAdapter()._chunks)
    assert ingested == in_memory


def test_no_chunk_starts_with_a_byte_order_mark():
    for strategy in ("lines", "words"):
        for chunk in collect_chunks(DOCS, 512, 50, strategy=strategy):
            assert not chunk["chunk"].startswith("﻿")


def test_word_windows_are_still_available_and_merge_a_short_file_into_one_chunk():
    words = collect_chunks(DOCS, 512, 50, strategy="words")
    assert len(words) == 4    # each file fits in one 512-word window


def test_doc_ids_use_forward_slashes_on_every_platform():
    assert all("\\" not in c["doc_id"] for c in collect_chunks(DOCS, 512, 50))


def test_an_unknown_strategy_is_rejected():
    with pytest.raises(ValueError):
        collect_chunks(DOCS, 512, 50, strategy="sentences")
