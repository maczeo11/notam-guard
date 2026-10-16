"""The regulation corpus: how it is chunked, and that what is checked in is sound.

The first half uses small synthetic documents to pin down the chunker's rules. The second half
guards the real corpus in data/regulations: every rule and form is present, the figures that
matter read correctly, and the committed chunks.jsonl matches a fresh build.
"""
import json

import pytest

from src import ingest, regulations as reg
from src.adapters.pgvector_adapter import InMemoryVectorAdapter
from src.core.config import reset_settings


def source(text, tmp_path, **extra):
    (tmp_path / "doc.txt").write_text(text, encoding="utf-8")
    spec = {"id": "doc", "file": "doc.txt", "short_title": "Sample Rules", "jurisdiction": "India",
            "kind": "rules", "unit_word": "Rule", **extra}
    return reg.build_source(spec, tmp_path)


def sentence(n, words=30):
    return f"Sentence {n} " + " ".join(["word"] * (words - 2)) + "."


# --- reading the format ------------------------------------------------------------------

def test_units_follow_the_headings_and_remember_their_group_and_page():
    title, units = reg.parse_document(
        "<<pdf 3>>\n# Sample Rules\n## PART I — GENERAL\n### 1. Short title\n(1) One.\n"
        "<<pdf 4>>\n### 2. Meaning\n(1) Two.\n")
    assert title == "Sample Rules"
    assert [u.heading for u in units] == ["1. Short title", "2. Meaning"]
    assert units[0].group == "PART I — GENERAL"
    assert units[0].lines[0][1] == 3 and units[1].lines[0][1] == 4


def test_a_sentence_that_runs_over_a_page_break_is_joined():
    _, units = reg.parse_document("<<pdf 3>>\n### 5. Break\nThe sentence starts here and\n<<pdf 4>>\ncontinues after the break.\n")
    assert reg._paragraphs(units[0]) == [("The sentence starts here and continues after the break.", 3)]


def test_a_new_item_after_a_page_break_is_not_glued_to_the_line_before():
    _, units = reg.parse_document("<<pdf 3>>\n### 5. Items\n(1) Lead in—\n<<pdf 4>>\n(a) first item;\n")
    assert [t for t, _ in reg._paragraphs(units[0])] == ["(1) Lead in—", "(a) first item;"]


# --- cutting into chunks -----------------------------------------------------------------

def test_a_short_rule_stays_in_one_chunk_with_a_header_naming_it(tmp_path):
    chunks = source("# Sample Rules\n## PART I — GENERAL\n### 22. Requirement of prior permission\n(1) No person shall fly.\n(2) Not in a green zone.\n", tmp_path)
    assert len(chunks) == 1
    assert chunks[0].ref == "Rule 22" and chunks[0].id == "doc:rule-22"
    assert chunks[0].text.startswith("Sample Rules, Part I, general — Rule 22 (Requirement of prior permission): (1) No person")


def test_a_long_rule_is_cut_between_sub_rules_never_inside_one(tmp_path):
    body = "\n".join(f"({n}) " + " ".join(["word"] * 40) + "." for n in range(1, 11))
    chunks = source(f"# T\n### 9. Long\n{body}\n", tmp_path)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.words <= reg.MAX_WORDS
        assert chunk.body().startswith("(") and chunk.body().endswith(".")
    assert [c.id for c in chunks] == [f"doc:rule-9~{i}" for i in range(1, len(chunks) + 1)]
    assert all(c.parts == len(chunks) for c in chunks) and "[part 2 of" in chunks[1].header


def test_a_long_paragraph_is_cut_between_sentences(tmp_path):
    paragraph = " ".join(sentence(n) for n in range(1, 13))
    chunks = source(f"# T\n### 1. Intro\n{paragraph}\n", tmp_path)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.words <= reg.MAX_WORDS
        assert chunk.body().endswith(".")
    assert " ".join(c.body() for c in chunks) == paragraph        # nothing lost, nothing repeated


def test_a_tiny_last_piece_is_folded_into_the_chunk_before_it(tmp_path):
    body = f"{sentence(1, 150)}\n(1) short tail."
    chunks = source(f"# T\n### 1. Fold\n{body}\n", tmp_path)
    assert len(chunks) == 1


def test_pages_are_recorded_for_the_text_a_chunk_covers(tmp_path):
    chunks = source("<<pdf 7>>\n# T\n### 1. A\n(1) First.\n<<pdf 8>>\n(2) Second.\n", tmp_path)
    assert chunks[0].pdf_pages == [7, 8]


# --- editorial notes ---------------------------------------------------------------------

def test_an_editorial_note_lands_on_the_chunk_it_is_about_and_says_it_is_not_the_rule(tmp_path):
    chunks = source("# T\n### 3. Defs\n(a) “licence” means the licence.\n### 4. Other\n(1) Other.\n", tmp_path,
                    annotations=[{"ref": "Rule 3", "note": "now reads certificate."}])
    assert "[Editorial note, not part of the rule: now reads certificate.]" in chunks[0].text
    assert "Editorial" not in chunks[1].text


def test_a_note_that_matches_nothing_is_an_error_so_it_cannot_silently_stop_applying(tmp_path):
    with pytest.raises(ValueError, match="matches no chunk"):
        source("# T\n### 3. Defs\n(1) text.\n", tmp_path, annotations=[{"ref": "Rule 99", "note": "x"}])


# --- the checked-in corpus ---------------------------------------------------------------

CHUNKS = reg.load_chunks()
MANIFEST = reg.load_manifest()


def by_ref(source_id, ref):
    return " ".join(c.text for c in CHUNKS if c.source == source_id and c.ref == ref)


def test_the_checked_in_chunks_match_a_fresh_build():
    assert reg.CHUNKS_PATH.read_text(encoding="utf-8") == reg.serialise(reg.build()), \
        "chunks.jsonl is out of date: run `python -m src.regulations build`"


def test_ids_are_unique_and_every_chunk_names_its_document():
    ids = [c.id for c in CHUNKS]
    assert len(ids) == len(set(ids))
    for chunk in CHUNKS:
        assert chunk.text.startswith(chunk.header + ": ") and chunk.title in chunk.header
        assert chunk.words > 0 and chunk.pdf_pages


def test_chunks_stay_a_readable_size():
    # MAX_WORDS for the body, plus room for an editorial note (up to about sixty words)
    assert max(c.words for c in CHUNKS) <= int(reg.MAX_WORDS * 1.5)


def test_all_fifty_five_rules_and_the_five_forms_of_the_drone_rules_are_present():
    refs = {c.ref for c in CHUNKS if c.source == "drone-rules-2021"}
    assert {f"Rule {n}" for n in range(1, 56)} <= refs
    assert {f"Form D-{n}" for n in range(1, 6)} <= refs


@pytest.mark.parametrize("ref,phrases", [
    ("Rule 3", ["upto a vertical distance of 400 feet or 120 metre",
                "upto a vertical distance of 200 feet or 60 metre",
                "between a lateral distance of 8 kilometre and 12 kilometre"]),
    ("Rule 5", ["Nano unmanned aircraft system: weighing less than or equal to 250 grams",
                "more than 250 grams, but less than or equal to 2 kilograms",
                "more than 2 kilograms, but less than or equal to 25 kilograms",
                "more than 25 kilograms, but less than or equal to 150 kilograms",
                "Large unmanned aircraft system: weighing more than 150 kilograms"]),
    ("Rule 19", ["horizontal resolution equal or finer than 10 meters"]),
    ("Rule 22", ["No person shall operate an unmanned aircraft system in a red zone or yellow zone without prior permission"]),
    ("Rule 24", ["not exceeding ninety six hours", "five kilometre"]),
    ("Rule 30", ["No later than forty-eight hours"]),
    ("Rule 46", ["Issuance of type certificate — 100", "Authorisation or renewal of authorisation of remote pilot training organisation — 1,000"]),
    ("Rule 49", ["Rule 22 and Rule 27 shall be cognizable and non-compoundable"]),
    ("Rule 50", ["a penalty not exceeding rupees one lakh"]),
])
def test_the_figures_that_matter_read_correctly(ref, phrases):
    text = by_ref("drone-rules-2021", ref)
    for phrase in phrases:
        assert phrase in text, f"{ref}: {phrase!r} is missing"


def test_the_amendments_are_there_and_the_rules_they_change_say_so():
    assert "on or before the thirty-first day of March, 2022" in by_ref("drone-amendment-rules-2022", "Rule 3")
    assert "sub-rule (4) shall be omitted" in by_ref("drone-amendment-rules-2022", "Rule 6")
    assert "Voter’s ID card, Ration Card or Driving License" in by_ref("drone-amendment-rules-2023", "Rule 2")
    assert "sub-rule (4) was omitted" in by_ref("drone-rules-2021", "Rule 34")
    notes = sum(c.text.count("[Editorial note, not part of the rule:") for c in CHUNKS)
    assert notes == len(MANIFEST["sources"][0]["annotations"])


def test_united_states_guidance_is_labelled_as_not_indian_law_in_every_chunk():
    foreign = [c for c in CHUNKS if c.jurisdiction != "India"]
    assert foreign and all("not Indian law" in c.header for c in foreign)


def test_every_source_in_the_manifest_records_where_it_came_from():
    for item in MANIFEST["sources"]:
        for key in ("source_url", "source_sha256", "method", "status", "licence_note", "omitted"):
            assert item.get(key), f"{item['id']}: {key} is missing"
        assert len(item["source_sha256"]) == 64
        assert any(c.source == item["id"] for c in CHUNKS), f"{item['id']} produced no chunks"


# --- using the corpus ---------------------------------------------------------------------

def test_load_chunks_refuses_a_missing_file_rather_than_returning_an_empty_corpus(tmp_path):
    with pytest.raises(FileNotFoundError, match="build"):
        reg.load_chunks(tmp_path / "nope.jsonl")


def test_the_sample_corpus_is_unchanged_unless_the_full_corpus_is_asked_for(monkeypatch):
    sample = InMemoryVectorAdapter()
    assert not any("Drone Rules, 2021" in chunk for chunk in sample._chunks)

    monkeypatch.setenv("CORPUS", "full")
    reset_settings()
    full = InMemoryVectorAdapter()
    assert len(full._chunks) == len(sample._chunks) + len(CHUNKS)
    assert "one lakh" in full.search("what is the maximum penalty rupees one lakh", 1)[0]


def test_lexical_retrieval_over_the_real_corpus_stays_above_its_measured_floor():
    """Measured at 12 of 18 (0.667) when the corpus was built. The misses are vocabulary gaps ("check" against
    "verify"), which is what embeddings are for. This only guards against the corpus getting worse."""
    store = InMemoryVectorAdapter([c.text for c in CHUNKS])
    queries = json.loads(reg.EVAL_PATH.read_text(encoding="utf-8"))
    rows = reg.retrieval_report(queries, lambda q, k: _search(store, q, k))
    hits = sum(1 for row in rows if row["rank"])
    assert hits / len(rows) >= 0.6, f"hit rate fell to {hits}/{len(rows)}"


def _search(store, query, k):
    from src.core.errors import RetrievalUnavailable
    try:
        return store.search(query, k)
    except RetrievalUnavailable:
        return []


def test_every_eval_question_points_at_text_that_exists():
    for item in json.loads(reg.EVAL_PATH.read_text(encoding="utf-8")):
        assert any(item["expect_contains"] in c.text for c in CHUNKS), f"no chunk contains {item['expect_contains']!r}"


def test_ingest_can_take_the_regulation_chunks_and_still_needs_something_to_ingest():
    rows = ingest.regulation_chunks()
    assert len(rows) == len(CHUNKS)
    assert rows[0]["doc_id"] == CHUNKS[0].id and rows[0]["chunk"] == CHUNKS[0].text
    with pytest.raises(SystemExit):
        ingest.main([])
