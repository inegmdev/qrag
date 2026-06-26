"""Unit tests for chunker.py — token-split logic."""
from pathlib import Path

import pytest

from qrag.chunker import CodeChunk, _split_large_chunk, _token_count, chunk_code_file

FIXTURE_C = Path(__file__).parent / "fixtures" / "sample.c"


def _make_chunk(text: str, name: str = "bigfunc") -> CodeChunk:
    return CodeChunk(
        symbol_name=name,
        file_path="test.c",
        line_start=1,
        line_end=text.count("\n") + 1,
        code_text=text,
        chunk_type="function",
    )


def test_token_count_basic():
    assert _token_count("a b c") == 3
    assert _token_count("") == 0


def test_token_count_trims_whitespace():
    assert _token_count("  hello  world  ") == 2


def test_split_single_chunk_when_small():
    chunk = _make_chunk("int foo() { return 0; }")
    result = _split_large_chunk(chunk)
    assert len(result) == 1
    assert result[0].symbol_name == "bigfunc#0"


def test_split_large_chunk_produces_multiple():
    lines = [f"int x{i} = {i}; /* tok tok tok tok tok tok tok tok */" for i in range(70)]
    text = "\n".join(lines)
    chunk = _make_chunk(text)
    assert _token_count(text) > 512, "fixture must exceed MAX_TOKENS"
    parts = _split_large_chunk(chunk)
    assert len(parts) >= 2


def test_split_sub_chunks_named_sequentially():
    lines = ["a b c d e f g h i j k l m n o p q r" for _ in range(60)]
    chunk = _make_chunk("\n".join(lines), name="myfunc")
    parts = _split_large_chunk(chunk)
    for i, p in enumerate(parts):
        assert p.symbol_name == f"myfunc#{i}"


def test_split_overlap_present():
    """Last lines of chunk N must appear in the start of chunk N+1."""
    lines = [f"int var_{i} = {i}; /* fill fill fill fill fill fill fill */" for i in range(70)]
    text = "\n".join(lines)
    chunk = _make_chunk(text)
    parts = _split_large_chunk(chunk)
    assert len(parts) >= 2, "need at least 2 parts to test overlap"
    last_of_first = set(parts[0].code_text.splitlines()[-5:])
    first_of_second = set(parts[1].code_text.splitlines()[:20])
    assert last_of_first & first_of_second, "no overlap found between consecutive sub-chunks"


def test_chunk_code_file_returns_functions():
    chunks = chunk_code_file(FIXTURE_C)
    names = {c.symbol_name for c in chunks}
    assert "enable_ecc" in names
    assert "sram_init" in names
    assert "disable_ecc" in names


def test_chunk_code_file_returns_macros():
    chunks = chunk_code_file(FIXTURE_C)
    names = {c.symbol_name for c in chunks}
    assert "ECC_BASE_ADDR" in names


def test_chunk_code_file_returns_structs():
    chunks = chunk_code_file(FIXTURE_C)
    struct_chunks = [c for c in chunks if c.chunk_type == "struct"]
    assert len(struct_chunks) >= 1


def test_chunk_code_file_all_types_present():
    chunks = chunk_code_file(FIXTURE_C)
    types = {c.chunk_type for c in chunks}
    assert "function" in types
    assert "macro" in types
    assert "struct" in types


def test_chunk_code_file_line_numbers_are_positive():
    chunks = chunk_code_file(FIXTURE_C)
    for c in chunks:
        assert c.line_start >= 1
        assert c.line_end >= c.line_start


def test_chunk_code_file_code_text_is_str():
    """Regression: GH#23 — tree-sitter-language-pack >=1.0 changed parse(bytes) to
    parse(str), causing 'bytes' object is not an instance of 'str' TypeError.
    All CodeChunk.code_text values must be str, never bytes."""
    chunks = chunk_code_file(FIXTURE_C)
    for c in chunks:
        assert isinstance(c.code_text, str), (
            f"code_text for {c.symbol_name!r} is {type(c.code_text).__name__}, expected str"
        )
