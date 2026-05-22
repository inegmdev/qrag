"""Unit tests for database.py — sqlite-vec BLOB round-trip and symbol upsert."""
import sqlite3

import pytest
import sqlite_vec

from raghub.database import (
    delete_chunks_for_file,
    get_symbol,
    init_code_db,
    insert_code_chunk,
    list_symbols,
    search_code,
)
from raghub.embedder import EMBEDDING_DIM, from_blob, to_blob


def _fake_embedding(val: float = 0.1) -> list[float]:
    return [val] * EMBEDDING_DIM


# ---------------------------------------------------------------------------
# BLOB round-trip
# ---------------------------------------------------------------------------


def test_to_blob_round_trip():
    emb = _fake_embedding(0.5)
    blob = to_blob(emb)
    recovered = from_blob(blob)
    assert len(recovered) == EMBEDDING_DIM
    assert all(abs(a - b) < 1e-6 for a, b in zip(emb, recovered))


def test_to_blob_byte_length():
    blob = to_blob(_fake_embedding())
    assert len(blob) == EMBEDDING_DIM * 4


def test_blob_survives_zero_values():
    emb = [0.0] * EMBEDDING_DIM
    assert from_blob(to_blob(emb)) == emb


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def test_init_creates_tables(tmp_path):
    db_path = tmp_path / "code.db"
    init_code_db(db_path)
    assert db_path.exists()
    db = sqlite3.connect(str(db_path))
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    tables = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "code_chunks" in tables
    assert "symbols" in tables
    db.close()


# ---------------------------------------------------------------------------
# Insert and lookup
# ---------------------------------------------------------------------------


def test_insert_and_get_symbol(tmp_path):
    db_path = tmp_path / "code.db"
    init_code_db(db_path)
    insert_code_chunk(
        db_path,
        symbol_name="my_func",
        file_path="foo.c",
        line_start=1,
        line_end=5,
        code_text="int my_func() { return 42; }",
        chunk_type="function",
        embedding=_fake_embedding(),
    )
    result = get_symbol(db_path, "my_func")
    assert result is not None
    assert result["symbol_name"] == "my_func"
    assert result["type"] == "function"
    assert "my_func" in result["code_text"]


def test_get_symbol_returns_none_for_missing(tmp_path):
    db_path = tmp_path / "code.db"
    init_code_db(db_path)
    assert get_symbol(db_path, "no_such_symbol") is None


# ---------------------------------------------------------------------------
# Symbol upsert on re-run
# ---------------------------------------------------------------------------


def test_symbol_upsert_on_rerun(tmp_path):
    """Re-running prepare on the same file keeps exactly one copy of each symbol."""
    db_path = tmp_path / "code.db"
    init_code_db(db_path)

    def _insert():
        delete_chunks_for_file(db_path, "foo.c")
        insert_code_chunk(
            db_path,
            symbol_name="my_func",
            file_path="foo.c",
            line_start=1,
            line_end=5,
            code_text="int my_func() { return 42; }",
            chunk_type="function",
            embedding=_fake_embedding(),
        )

    _insert()
    _insert()
    _insert()

    syms = list_symbols(db_path)
    assert sum(1 for s in syms if s["name"] == "my_func") == 1


def test_upsert_preserves_other_files(tmp_path):
    """Deleting file A's chunks must not remove file B's chunks."""
    db_path = tmp_path / "code.db"
    init_code_db(db_path)

    for fname, sym in [("a.c", "func_a"), ("b.c", "func_b")]:
        insert_code_chunk(
            db_path, sym, fname, 1, 2,
            f"void {sym}() {{}}", "function", _fake_embedding(),
        )

    delete_chunks_for_file(db_path, "a.c")
    insert_code_chunk(
        db_path, "func_a", "a.c", 1, 2, "void func_a() {}", "function", _fake_embedding(),
    )

    names = {s["name"] for s in list_symbols(db_path)}
    assert "func_a" in names
    assert "func_b" in names


# ---------------------------------------------------------------------------
# list_symbols filtering
# ---------------------------------------------------------------------------


def test_list_symbols_pattern_filter(tmp_path):
    db_path = tmp_path / "code.db"
    init_code_db(db_path)

    for name in ["ecc_enable", "ecc_disable", "sram_init"]:
        insert_code_chunk(
            db_path, name, "test.c", 1, 2,
            f"void {name}() {{}}", "function", _fake_embedding(),
        )

    ecc_syms = list_symbols(db_path, pattern="ecc")
    assert len(ecc_syms) == 2
    assert all("ecc" in s["name"] for s in ecc_syms)


def test_list_symbols_no_filter_returns_all(tmp_path):
    db_path = tmp_path / "code.db"
    init_code_db(db_path)

    for name in ["alpha", "beta", "gamma"]:
        insert_code_chunk(
            db_path, name, "test.c", 1, 2,
            f"void {name}() {{}}", "function", _fake_embedding(),
        )

    assert len(list_symbols(db_path)) == 3


# ---------------------------------------------------------------------------
# search_code ranking
# ---------------------------------------------------------------------------


def test_search_code_top_result_matches_query(tmp_path):
    """Symbol whose embedding matches the query should rank first."""
    db_path = tmp_path / "code.db"
    init_code_db(db_path)

    emb_a = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
    emb_b = [0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2)

    insert_code_chunk(db_path, "func_a", "a.c", 1, 2, "void func_a(){}", "function", emb_a)
    insert_code_chunk(db_path, "func_b", "b.c", 1, 2, "void func_b(){}", "function", emb_b)

    results = search_code(db_path, emb_a, top_k=2)
    assert len(results) >= 1
    assert results[0]["symbol_name"] == "func_a"
