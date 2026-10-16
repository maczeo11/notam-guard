"""Looking a rule up by identifier, as opposed to searching for it by similarity."""
import pytest

from src.adapters.pgvector_adapter import InMemoryVectorAdapter, PgVectorAdapter
from src.core.errors import RetrievalUnavailable

CLAUSE_7 = "§7 Micro RPA ( <2kg ): Max altitude 120m AGL, UIN required."
CLAUSE_70 = "§70 A different clause that merely starts with the same digits."
CRANE = "NOTAM 09/03 Pune Site: Crane 100m at 18.53,73.84 radius 1km. DGCA CAR §7 applies."
BIRDS = "NOTAM 09/05 Bird activity reported 18.55,73.86 radius 2km."
CORPUS = [CLAUSE_70, CRANE, CLAUSE_7, BIRDS]


def test_lookup_returns_the_chunk_that_defines_a_rule_and_not_one_that_mentions_it():
    store = InMemoryVectorAdapter(CORPUS)
    assert store.lookup(["CAR §7"]) == [CLAUSE_7]          # not CRANE, not CLAUSE_70


def test_lookup_finds_a_notam_by_its_id():
    assert InMemoryVectorAdapter(CORPUS).lookup(["NOTAM 09/03"]) == [CRANE]


def test_lookup_of_several_references_keeps_corpus_order_and_drops_repeats():
    store = InMemoryVectorAdapter(CORPUS)
    assert store.lookup(["NOTAM 09/05", "CAR §7", "CAR §7"]) == [CLAUSE_7, BIRDS]


def test_lookup_of_an_unknown_reference_returns_nothing():
    assert InMemoryVectorAdapter(CORPUS).lookup(["NOTAM 12/99"]) == []


def test_lookup_of_no_references_returns_nothing():
    assert InMemoryVectorAdapter(CORPUS).lookup([]) == []


class FakeCursor:
    """Answers `ILIKE` queries from a list of chunks, like Postgres would, and records them."""

    def __init__(self, chunks, log, fail):
        self._chunks, self._log, self._fail, self._rows = chunks, log, fail, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        if self._fail:
            raise RuntimeError("connection reset")
        self._log.append((sql, params))
        needle = params[0][1:-1].replace("\\%", "%").replace("\\_", "_").lower()
        self._rows = [(c,) for c in self._chunks if needle in c.lower()]

    def fetchall(self):
        return self._rows


class FakeConnection:
    closed = False

    def __init__(self, chunks, fail=False):
        self.log, self._chunks, self._fail = [], chunks, fail

    def cursor(self):
        return FakeCursor(self._chunks, self.log, self._fail)


def pg_with(chunks, fail=False):
    adapter = PgVectorAdapter()
    connection = FakeConnection(chunks, fail)
    adapter._conn = connection
    adapter._get_conn = lambda: connection
    return adapter, connection


def test_the_pgvector_lookup_prefilters_in_sql_then_applies_the_exact_rule():
    adapter, connection = pg_with(CORPUS)
    assert adapter.lookup(["CAR §7"]) == [CLAUSE_7]
    sql, params = connection.log[0]
    assert "ILIKE" in sql and "%s" in sql, "the reference must be a bound parameter"
    assert params == ("%§7%",)


def test_the_pgvector_lookup_escapes_like_wildcards_in_a_reference():
    adapter, connection = pg_with(CORPUS)
    adapter.lookup(["100%_match"])
    assert connection.log[0][1] == ("%100\\%\\_match%",)


def test_the_pgvector_lookup_of_no_references_does_not_touch_the_database():
    adapter, connection = pg_with(CORPUS)
    assert adapter.lookup([]) == []
    assert connection.log == []


def test_a_database_error_during_lookup_is_a_retrieval_failure_not_an_empty_result():
    adapter, _ = pg_with(CORPUS, fail=True)
    with pytest.raises(RetrievalUnavailable):
        adapter.lookup(["CAR §7"])
    assert adapter._conn is None, "a failed connection must be dropped so the next call reconnects"
