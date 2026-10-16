"""The regulation corpus: real documents, split into units a citation can point at.

`data/regulations/text/` holds each source as plain text in one small format:

    <<pdf 12>>            the following text starts on page 12 of the source file
    # Document title
    ## PART V - GROUP     a group of units (a Part, a chapter)
    ### 22. Heading       one unit: a rule, a section, a form
    paragraph lines...    one paragraph per line; "(1)", "(a)" and "- " lines belong to the one before

`manifest.json` says where each file came from. `chunks.jsonl` is what `build` produces and is
checked in, so the corpus can be loaded without rebuilding. Chunking follows the document's own
structure instead of cutting fixed windows: a rule is a chunk, a long rule is cut between
sub-rules, and a long paragraph is cut between sentences. Every chunk starts with a header naming
the document, the group and the unit, because a sub-rule on its own ("(2) No prior permission
shall be required...") means nothing to a reader or to a similarity search.

    python -m src.regulations build      # rewrite chunks.jsonl from text/ and manifest.json
    python -m src.regulations check      # fail if chunks.jsonl is out of date
    python -m src.regulations stats      # chunks and words per source
    python -m src.regulations eval       # retrieval hit rate on data/regulations/eval_queries.json
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
import argparse
import json
import re
import sys

from src.core.config import REPO_ROOT

REG_DIR = REPO_ROOT / "data" / "regulations"
MANIFEST_PATH = REG_DIR / "manifest.json"
CHUNKS_PATH = REG_DIR / "chunks.jsonl"
EVAL_PATH = REG_DIR / "eval_queries.json"

#: Upper bound for the body of one chunk, in words. A rule shorter than this stays whole.
MAX_WORDS = 170
#: A trailing piece smaller than this is folded into the chunk before it when that fits.
MIN_TAIL_WORDS = 30

_PAGE = re.compile(r"^<<pdf (\d+)>>$")
_SUB_RULE = re.compile(r"^\(\d+[A-Za-z]?\)")
_ITEM = re.compile(r"^(?:\([a-z]{1,2}\)|\([ivx]+\)|[a-z]{1,2}\) |[ivx]+\) |- |Provided\b|Note\b)")
_SENTENCE_END = re.compile(r"(?<=[.;:?!])\s+(?=[A-Z(“‘0-9])")
_NUMBERED = re.compile(r"^(?P<num>\d+(?:\.\d+)*)\.?\s+(?P<title>.+)$")
_FORM = re.compile(r"^FORM (?P<id>D-\d+) — (?P<title>.+)$")


@dataclass
class Chunk:
    id: str
    source: str
    title: str
    jurisdiction: str
    kind: str
    group: str
    ref: str
    heading: str
    header: str
    part: int
    parts: int
    pdf_pages: List[int]
    words: int
    text: str

    def body(self) -> str:
        """The text without its header."""
        return self.text[len(self.header) + 2:]

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)


@dataclass
class _Unit:
    heading: str
    group: str
    lines: List[Tuple[str, int, bool]] = field(default_factory=list)   # text, page, starts after a page break


# --------------------------------------------------------------------------------------
# reading the text format
# --------------------------------------------------------------------------------------

def parse_document(text: str) -> Tuple[str, List[_Unit]]:
    """The document title and its units, each with its lines and the page every line starts on."""
    title, group, page, page_break = "", "", 1, False
    units: List[_Unit] = []
    current: Optional[_Unit] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if marker := _PAGE.match(line):
            page, page_break = int(marker.group(1)), True
        elif line.startswith("### "):
            current = _Unit(heading=line[4:].strip(), group=group)
            units.append(current)
            page_break = False
        elif line.startswith("## "):
            group, current = line[3:].strip(), None
        elif line.startswith("# "):
            title = line[2:].strip()
        else:
            if current is None:                      # text under a group heading and before its first unit
                current = _Unit(heading=group or title, group=group)
                units.append(current)
            current.lines.append((line, page, page_break))
            page_break = False
    return title, units


def _paragraphs(unit: _Unit) -> List[Tuple[str, int]]:
    """Source lines, with a sentence that ran across a page break put back together."""
    paragraphs: List[Tuple[str, int]] = []
    for text, page, after_break in unit.lines:
        continues = after_break and paragraphs and text[:1].islower() and not _ITEM.match(text)
        if continues:
            previous, first_page = paragraphs[-1]
            paragraphs[-1] = (f"{previous} {text}", first_page)
        else:
            paragraphs.append((text, page))
    return paragraphs


def _words(text: str) -> int:
    return len(text.split())


def _blocks(paragraphs: List[Tuple[str, int]]) -> List[List[Tuple[str, int]]]:
    """Paragraphs grouped so a sub-rule stays with its own (a), (b) items."""
    blocks: List[List[Tuple[str, int]]] = []
    for text, page in paragraphs:
        starts_new = not blocks or _SUB_RULE.match(text) or not _ITEM.match(text)
        if starts_new:
            blocks.append([(text, page)])
        else:
            blocks[-1].append((text, page))
    return blocks


def _split_long(text: str, page: int) -> List[Tuple[str, int]]:
    """Cut one over-long paragraph between sentences, never inside one."""
    sentences = _SENTENCE_END.split(text)
    pieces, current = [], ""
    for sentence in sentences:
        if current and _words(current) + _words(sentence) > MAX_WORDS:
            pieces.append((current, page))
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append((current, page))
    return pieces


def _pack(paragraphs: List[Tuple[str, int]]) -> List[List[Tuple[str, int]]]:
    """Fill chunks up to MAX_WORDS, cutting between blocks first, then between paragraphs, then sentences."""
    units: List[Tuple[int, List[Tuple[str, int]]]] = []          # (words, paragraphs) pieces that must stay whole
    for block in _blocks(paragraphs):
        words = sum(_words(t) for t, _ in block)
        if words <= MAX_WORDS:
            units.append((words, block))
            continue
        for text, page in block:
            if _words(text) <= MAX_WORDS:
                units.append((_words(text), [(text, page)]))
            else:
                units.extend((_words(t), [(t, p)]) for t, p in _split_long(text, page))

    chunks: List[List[Tuple[str, int]]] = []
    sizes: List[int] = []
    for words, paras in units:
        if chunks and sizes[-1] + words <= MAX_WORDS:
            chunks[-1].extend(paras)
            sizes[-1] += words
        else:
            chunks.append(list(paras))
            sizes.append(words)
    if len(chunks) > 1 and sizes[-1] < MIN_TAIL_WORDS and sizes[-2] + sizes[-1] <= MAX_WORDS * 1.3:
        chunks[-2].extend(chunks.pop())
    return chunks


# --------------------------------------------------------------------------------------
# naming
# --------------------------------------------------------------------------------------

def _label(heading: str, unit_word: str) -> Tuple[str, str]:
    """('Rule 22', 'Requirement of prior permission') for '22. Requirement of prior permission'."""
    if form := _FORM.match(heading):
        return f"Form {form.group('id')}", form.group("title")
    if numbered := _NUMBERED.match(heading):
        number = numbered.group("num")
        word = "Section" if "." in number and unit_word == "Section" else unit_word
        return f"{word} {number}", numbered.group("title")
    return heading, ""


def _slug(ref: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", ref.lower()).strip("-")


def _short_group(group: str) -> str:
    """'PART V — OPERATION OF UNMANNED AIRCRAFT SYSTEM' -> 'Part V, operation of unmanned aircraft system'."""
    if " — " not in group:
        return group
    head, _, tail = group.partition(" — ")
    if head.upper().startswith("PART "):
        return f"Part {head[5:]}, {tail.lower()}"          # keeps the roman numeral in capitals
    return group


# --------------------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------------------

def build_source(source: dict, base_dir: Path = REG_DIR) -> List[Chunk]:
    """The chunks of one source, with its editorial notes attached."""
    text = (base_dir / source["file"]).read_text(encoding="utf-8")
    _, units = parse_document(text)
    chunks: List[Chunk] = []
    for unit in units:
        paragraphs = _paragraphs(unit)
        if not paragraphs:
            continue
        ref, title = _label(unit.heading, source.get("unit_word", "Section"))
        parts = _pack(paragraphs)
        for index, part in enumerate(parts, 1):
            name = f"{source['short_title']}"
            if unit.group and source.get("kind") in ("rules", "policy"):
                name += f", {_short_group(unit.group)}"
            heading = f"{name} — {ref}" + (f" ({title})" if title else "")
            if len(parts) > 1:
                heading += f" [part {index} of {len(parts)}]"
            body = " ".join(t for t, _ in part)
            slug = _slug(ref) + (f"~{index}" if len(parts) > 1 else "")
            chunks.append(Chunk(
                id=f"{source['id']}:{slug}", source=source["id"], title=source["short_title"],
                jurisdiction=source["jurisdiction"], kind=source["kind"], group=unit.group,
                ref=ref, heading=title or ref, header=heading, part=index, parts=len(parts),
                pdf_pages=sorted({p for _, p in part}), words=_words(body),
                text=f"{heading}: {body}"))
    _annotate(chunks, source.get("annotations", []), source["id"])
    return chunks


def _annotate(chunks: List[Chunk], annotations: Sequence[dict], source_id: str) -> None:
    """Append each editorial note to the chunk it is about. A note that matches nothing is an error,
    so a note cannot silently stop applying when the text changes."""
    for note in annotations:
        candidates = [c for c in chunks if c.ref == note["ref"]]
        if "contains" in note:
            candidates = [c for c in candidates if note["contains"] in c.text]
        if not candidates:
            raise ValueError(f"{source_id}: editorial note for {note['ref']!r} matches no chunk: {note}")
        target = candidates[-1] if "contains" not in note else candidates[0]
        target.text += f" [Editorial note, not part of the rule: {note['note']}]"
        target.words = _words(target.body())


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(manifest: Optional[dict] = None, base_dir: Path = REG_DIR) -> List[Chunk]:
    manifest = manifest or load_manifest()
    chunks: List[Chunk] = []
    for source in manifest["sources"]:
        chunks.extend(build_source(source, base_dir))
    ids = [c.id for c in chunks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate chunk ids: {sorted(duplicates)[:5]}")
    return chunks


def serialise(chunks: Iterable[Chunk]) -> str:
    return "".join(chunk.to_json() + "\n" for chunk in chunks)


def load_chunks(path: Path = CHUNKS_PATH) -> List[Chunk]:
    """The built corpus. Raises if it has not been built, because an empty corpus must not pass for a real one."""
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing: run `python -m src.regulations build`")
    return [Chunk(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------------------
# measuring retrieval on the real corpus
# --------------------------------------------------------------------------------------

def retrieval_report(queries: Sequence[dict], search: Callable[[str, int], List[str]], k: int = 3) -> List[dict]:
    """For each query, whether the top-k chunks include one containing the expected phrase."""
    rows = []
    for item in queries:
        found = search(item["query"], k)
        hit = next((i for i, chunk in enumerate(found, 1) if item["expect_contains"] in chunk), None)
        rows.append({"query": item["query"], "expect": item["expect_contains"], "rank": hit})
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build and inspect the regulation corpus")
    parser.add_argument("command", choices=["build", "check", "stats", "eval"])
    args = parser.parse_args(argv)

    if args.command in ("build", "check"):
        text = serialise(build())
        if args.command == "build":
            CHUNKS_PATH.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {CHUNKS_PATH} ({text.count(chr(10))} chunks)")
            return 0
        current = CHUNKS_PATH.read_text(encoding="utf-8") if CHUNKS_PATH.is_file() else ""
        if current != text:
            print("chunks.jsonl is out of date: run `python -m src.regulations build`")
            return 1
        print("chunks.jsonl is up to date")
        return 0

    chunks = load_chunks()
    if args.command == "stats":
        by_source: Dict[str, List[Chunk]] = {}
        for chunk in chunks:
            by_source.setdefault(chunk.source, []).append(chunk)
        for source, items in by_source.items():
            words = [c.words for c in items]
            print(f"{source:34} {len(items):4} chunks  {sum(words):6} words  "
                  f"min {min(words):3}  median {sorted(words)[len(words) // 2]:3}  max {max(words):3}")
        print(f"{'total':34} {len(chunks):4} chunks  {sum(c.words for c in chunks):6} words")
        return 0

    from src.adapters.pgvector_adapter import InMemoryVectorAdapter       # lexical search, no database needed
    from src.core.errors import RetrievalUnavailable
    store = InMemoryVectorAdapter([c.text for c in chunks])
    queries = json.loads(EVAL_PATH.read_text(encoding="utf-8"))

    def search(query: str, k: int) -> List[str]:
        try:
            return store.search(query, k)
        except RetrievalUnavailable:                                       # nothing matched: that is a miss
            return []

    rows = retrieval_report(queries, search)
    for row in rows:
        print(f"{'hit @' + str(row['rank']) if row['rank'] else 'MISS':8} {row['query']}")
    hits = sum(1 for r in rows if r["rank"])
    print(f"\ntop-3 hit rate: {hits}/{len(rows)} = {hits / len(rows):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
