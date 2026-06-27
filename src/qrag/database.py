from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import sqlite_vec

from .embedder import EMBEDDING_DIM, to_blob


def _open(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(db_path))
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.row_factory = sqlite3.Row
    return db


_CODE_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, type)
    ("code_chunks", "language",    "TEXT"),
    ("symbols",     "language",    "TEXT"),
    ("code_chunks", "file_name",   "TEXT"),
    ("code_chunks", "parent_name", "TEXT"),
    ("code_chunks", "call_depth",  "INTEGER"),
    ("code_chunks", "chunk_index", "INTEGER"),
]


def _open_code(db_path: Path) -> sqlite3.Connection:
    """Open a code DB and migrate schema if needed."""
    db = _open(db_path)
    for table, col, col_type in _CODE_MIGRATIONS:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            db.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    return db


def init_code_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = _open(db_path)
    try:
        db.executescript(f"""
            CREATE TABLE IF NOT EXISTS code_chunks (
                id          INTEGER PRIMARY KEY,
                symbol_name TEXT,
                file_path   TEXT,
                file_name   TEXT,
                line_start  INTEGER,
                line_end    INTEGER,
                code_text   TEXT,
                type        TEXT,
                language    TEXT,
                parent_name TEXT,
                call_depth  INTEGER DEFAULT 0,
                chunk_index INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS symbols (
                id          INTEGER PRIMARY KEY,
                name        TEXT UNIQUE,
                type        TEXT,
                language    TEXT,
                file_path   TEXT,
                line_number INTEGER,
                chunk_id    INTEGER REFERENCES code_chunks(id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_code USING vec0(
                chunk_id INTEGER,
                embedding float[{EMBEDDING_DIM}] distance_metric=cosine
            );
            CREATE TABLE IF NOT EXISTS file_manifest (
                rel_path   TEXT NOT NULL,
                input_root TEXT NOT NULL,
                mtime      REAL NOT NULL,
                sha256     TEXT NOT NULL,
                PRIMARY KEY (rel_path, input_root)
            );
        """)
        db.commit()
    finally:
        db.close()


def delete_chunks_for_file(db_path: Path, file_path: str) -> None:
    """Remove all chunks and vectors belonging to a file (for upsert on re-run)."""
    db = _open_code(db_path)
    try:
        rows = db.execute(
            "SELECT id FROM code_chunks WHERE file_path = ?", (file_path,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            placeholders = ",".join("?" * len(ids))
            db.execute(f"DELETE FROM vec_code WHERE chunk_id IN ({placeholders})", ids)
            db.execute(f"DELETE FROM symbols WHERE chunk_id IN ({placeholders})", ids)
            db.execute(f"DELETE FROM code_chunks WHERE id IN ({placeholders})", ids)
        db.commit()
    finally:
        db.close()


def insert_code_chunk(
    db_path: Path,
    symbol_name: str,
    file_path: str,
    line_start: int,
    line_end: int,
    code_text: str,
    chunk_type: str,
    embedding: list[float],
    language: str = "",
    parent_name: str = "",
    call_depth: int = 0,
    chunk_index: int = 0,
) -> int:
    from pathlib import Path as _Path
    file_name = _Path(file_path).name
    db = _open_code(db_path)
    try:
        cur = db.execute(
            """
            INSERT INTO code_chunks
              (symbol_name, file_path, file_name, line_start, line_end, code_text,
               type, language, parent_name, call_depth, chunk_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol_name, file_path, file_name, line_start, line_end, code_text,
             chunk_type, language, parent_name, call_depth, chunk_index),
        )
        chunk_id = cur.lastrowid

        db.execute(
            "INSERT OR REPLACE INTO symbols (name, type, language, file_path, line_number, chunk_id) VALUES (?,?,?,?,?,?)",
            (symbol_name, chunk_type, language, file_path, line_start, chunk_id),
        )

        db.execute(
            "INSERT INTO vec_code (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, to_blob(embedding)),
        )

        db.commit()
    finally:
        db.close()
    return chunk_id


def insert_code_chunks_batch(
    db_path: Path,
    chunks: list,
    embeddings: list[list[float]],
) -> None:
    """Insert a batch of CodeChunk objects and their embeddings in a single transaction."""
    from pathlib import Path as _Path
    db = _open_code(db_path)
    try:
        for chunk, emb in zip(chunks, embeddings):
            lang = getattr(chunk, "language", "")
            file_name = _Path(chunk.file_path).name
            parent_name = getattr(chunk, "parent_name", "")
            call_depth = getattr(chunk, "call_depth", 0)
            chunk_index = getattr(chunk, "chunk_index", 0)
            cur = db.execute(
                """
                INSERT INTO code_chunks
                  (symbol_name, file_path, file_name, line_start, line_end, code_text,
                   type, language, parent_name, call_depth, chunk_index)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (chunk.symbol_name, chunk.file_path, file_name,
                 chunk.line_start, chunk.line_end, chunk.code_text,
                 chunk.chunk_type, lang, parent_name, call_depth, chunk_index),
            )
            chunk_id = cur.lastrowid
            db.execute(
                "INSERT OR REPLACE INTO symbols (name, type, language, file_path, line_number, chunk_id) VALUES (?,?,?,?,?,?)",
                (chunk.symbol_name, chunk.chunk_type, lang, chunk.file_path, chunk.line_start, chunk_id),
            )
            db.execute(
                "INSERT INTO vec_code (chunk_id, embedding) VALUES (?,?)",
                (chunk_id, to_blob(emb)),
            )
        db.commit()
    finally:
        db.close()


_DOCS_MIGRATIONS: list[tuple[str, str]] = [
    # (column, type)
    ("doc_name",      "TEXT"),
    ("doc_revision",  "TEXT"),
    ("doc_status",    "TEXT"),
    ("word_count",    "INTEGER"),
    ("fig_table_refs","TEXT"),
]


def _open_docs(db_path: Path) -> sqlite3.Connection:
    """Open a docs DB and migrate schema if needed."""
    db = _open(db_path)
    for col, col_type in _DOCS_MIGRATIONS:
        try:
            db.execute(f"ALTER TABLE doc_sections ADD COLUMN {col} {col_type}")
            db.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    return db


def insert_doc_sections_batch(
    db_path: Path,
    sections: list,
    embeddings: list[list[float]],
) -> None:
    """Insert a batch of DocSection objects and their embeddings in a single transaction."""
    db = _open_docs(db_path)
    try:
        for sec, emb in zip(sections, embeddings):
            cur = db.execute(
                """
                INSERT INTO doc_sections
                  (source_path, doc_type, chapter, section, subsection,
                   title, content, page_range, feature_tags,
                   doc_name, doc_revision, doc_status, word_count, fig_table_refs)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (sec.source_path, sec.doc_type, sec.chapter, sec.section, sec.subsection,
                 sec.title, sec.content, sec.page_range, sec.feature_tags,
                 getattr(sec, "doc_name", ""), getattr(sec, "doc_revision", ""),
                 getattr(sec, "doc_status", ""), getattr(sec, "word_count", 0),
                 getattr(sec, "fig_table_refs", "")),
            )
            section_id = cur.lastrowid
            db.execute(
                "INSERT INTO vec_docs (section_id, embedding) VALUES (?,?)",
                (section_id, to_blob(emb)),
            )
        db.commit()
    finally:
        db.close()


def upsert_manifest_rows_batch(
    db_path: Path,
    rows: list[tuple[str, str, float, str]],
) -> None:
    """Upsert many manifest rows in a single transaction.

    Each row is (rel_path, input_root, mtime, sha256).
    """
    if not rows:
        return
    db = _open(db_path)
    try:
        db.executemany(
            "INSERT OR REPLACE INTO file_manifest (rel_path, input_root, mtime, sha256) VALUES (?,?,?,?)",
            rows,
        )
        db.commit()
    finally:
        db.close()


def get_symbol(db_path: Path, name: str) -> dict | None:
    db = _open_code(db_path)
    try:
        row = db.execute(
            """
            SELECT c.symbol_name, c.type, c.language, c.file_path, c.line_start, c.line_end, c.code_text
            FROM symbols s
            JOIN code_chunks c ON c.id = s.chunk_id
            WHERE s.name = ?
            """,
            (name,),
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return None
    return dict(row)


def list_symbols(db_path: Path, pattern: str = "", limit: int = 200) -> list[dict[str, Any]]:
    db = _open_code(db_path)
    try:
        if pattern:
            rows = db.execute(
                """
                SELECT name, type, language, file_path, line_number
                FROM symbols
                WHERE name LIKE ?
                ORDER BY name
                LIMIT ?
                """,
                (f"%{pattern}%", limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT name, type, language, file_path, line_number
                FROM symbols
                ORDER BY name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    finally:
        db.close()

    results = []
    for row in rows:
        results.append({
            "name": row["name"],
            "type": row["type"],
            "language": row["language"] or "",
            "file": row["file_path"],
            "line": row["line_number"],
        })
    return results


def init_docs_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = _open(db_path)
    try:
        db.executescript(f"""
            CREATE TABLE IF NOT EXISTS doc_sections (
                id            INTEGER PRIMARY KEY,
                source_path   TEXT,
                doc_type      TEXT,
                chapter       INTEGER,
                section       INTEGER,
                subsection    TEXT,
                title         TEXT,
                content       TEXT,
                page_range    TEXT,
                feature_tags  TEXT,
                doc_name      TEXT,
                doc_revision  TEXT,
                doc_status    TEXT,
                word_count    INTEGER,
                fig_table_refs TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_docs USING vec0(
                section_id INTEGER,
                embedding float[{EMBEDDING_DIM}] distance_metric=cosine
            );
            CREATE TABLE IF NOT EXISTS file_manifest (
                rel_path   TEXT NOT NULL,
                input_root TEXT NOT NULL,
                mtime      REAL NOT NULL,
                sha256     TEXT NOT NULL,
                PRIMARY KEY (rel_path, input_root)
            );
        """)
        db.commit()
    finally:
        db.close()


def load_manifest(db_path: Path) -> dict[tuple[str, str], tuple[float, str]]:
    """Return {(input_root, rel_path): (mtime, sha256)} for all rows in file_manifest."""
    if not db_path.exists():
        return {}
    db = _open(db_path)
    try:
        rows = db.execute(
            "SELECT input_root, rel_path, mtime, sha256 FROM file_manifest"
        ).fetchall()
    finally:
        db.close()
    return {(r["input_root"], r["rel_path"]): (r["mtime"], r["sha256"]) for r in rows}


def upsert_manifest_row(
    db_path: Path, rel_path: str, input_root: str, mtime: float, sha256: str
) -> None:
    db = _open(db_path)
    try:
        db.execute(
            "INSERT OR REPLACE INTO file_manifest (rel_path, input_root, mtime, sha256) VALUES (?,?,?,?)",
            (rel_path, input_root, mtime, sha256),
        )
        db.commit()
    finally:
        db.close()


def delete_manifest_row(db_path: Path, rel_path: str, input_root: str) -> None:
    db = _open(db_path)
    try:
        db.execute(
            "DELETE FROM file_manifest WHERE rel_path = ? AND input_root = ?",
            (rel_path, input_root),
        )
        db.commit()
    finally:
        db.close()


def delete_sections_for_source(db_path: Path, source_path: str) -> None:
    """Remove all doc_sections and vectors for a source file (upsert support)."""
    db = _open_docs(db_path)
    try:
        rows = db.execute(
            "SELECT id FROM doc_sections WHERE source_path = ?", (source_path,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            placeholders = ",".join("?" * len(ids))
            db.execute(f"DELETE FROM vec_docs WHERE section_id IN ({placeholders})", ids)
            db.execute(f"DELETE FROM doc_sections WHERE id IN ({placeholders})", ids)
        db.commit()
    finally:
        db.close()


def insert_doc_section(
    db_path: Path,
    source_path: str,
    doc_type: str,
    chapter: int,
    section: int,
    subsection: str,
    title: str,
    content: str,
    page_range: str,
    feature_tags: str,
    embedding: list[float],
    doc_name: str = "",
    doc_revision: str = "",
    doc_status: str = "",
    word_count: int = 0,
    fig_table_refs: str = "",
) -> int:
    db = _open_docs(db_path)
    try:
        cur = db.execute(
            """
            INSERT INTO doc_sections
              (source_path, doc_type, chapter, section, subsection,
               title, content, page_range, feature_tags,
               doc_name, doc_revision, doc_status, word_count, fig_table_refs)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (source_path, doc_type, chapter, section, subsection,
             title, content, page_range, feature_tags,
             doc_name, doc_revision, doc_status, word_count, fig_table_refs),
        )
        section_id = cur.lastrowid
        db.execute(
            "INSERT INTO vec_docs (section_id, embedding) VALUES (?, ?)",
            (section_id, to_blob(embedding)),
        )
        db.commit()
    finally:
        db.close()
    return section_id


def search_docs(db_path: Path, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    db = _open_docs(db_path)
    try:
        rows = db.execute(
            """
            SELECT
                d.source_path, d.doc_type, d.doc_name, d.doc_revision, d.doc_status,
                d.chapter, d.section, d.subsection, d.title,
                d.content, d.page_range, d.feature_tags,
                d.word_count, d.fig_table_refs,
                v.distance
            FROM vec_docs v
            JOIN doc_sections d ON d.id = v.section_id
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (to_blob(query_embedding), top_k),
        ).fetchall()
    finally:
        db.close()

    results = []
    for row in rows:
        similarity = max(0.0, 1.0 - row["distance"])
        tags = row["feature_tags"] or ""
        refs = row["fig_table_refs"] or ""
        results.append({
            "source_path": row["source_path"] or "",
            "doc_name": row["doc_name"] or "",
            "doc_revision": row["doc_revision"] or "",
            "doc_status": row["doc_status"] or "",
            "doc_type": row["doc_type"],
            "chapter": row["chapter"],
            "section": row["section"],
            "subsection": row["subsection"] or "",
            "title": row["title"],
            "content": row["content"][:400],
            "page_range": row["page_range"] or "",
            "feature_tags": [t for t in tags.split(",") if t] if tags else [],
            "word_count": row["word_count"] or 0,
            "fig_table_refs": [r for r in refs.split(",") if r] if refs else [],
            "similarity_score": round(similarity, 4),
        })
    return results


def search_code(db_path: Path, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    db = _open_code(db_path)
    try:
        rows = db.execute(
            """
            SELECT
                c.symbol_name,
                c.file_path,
                c.file_name,
                c.line_start,
                c.line_end,
                c.code_text,
                c.type,
                c.language,
                c.parent_name,
                c.call_depth,
                c.chunk_index,
                v.distance
            FROM vec_code v
            JOIN code_chunks c ON c.id = v.chunk_id
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (to_blob(query_embedding), top_k),
        ).fetchall()
    finally:
        db.close()

    results = []
    for row in rows:
        similarity = max(0.0, 1.0 - row["distance"])
        results.append(
            {
                "symbol_name": row["symbol_name"],
                "file_path": row["file_path"],
                "file_name": row["file_name"] or "",
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "code_snippet": row["code_text"][:300],
                "type": row["type"],
                "language": row["language"] or "",
                "parent_name": row["parent_name"] or "",
                "call_depth": row["call_depth"] or 0,
                "chunk_index": row["chunk_index"] or 0,
                "similarity_score": round(similarity, 4),
            }
        )
    return results


# ---------------------------------------------------------------------------
# Explore stats helpers
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "of", "to", "in", "is", "it", "on", "at", "be",
    "do", "go", "if", "or", "and", "for", "not", "are", "was", "with",
    "from", "this", "that", "have", "has", "had", "can", "will",
    "ret", "val", "var", "tmp", "ptr", "buf", "len", "num", "max", "min",
    "get", "set", "new", "del", "err", "res", "idx", "cnt", "str", "int",
    "msg", "cfg", "ctx", "obj", "ref", "key", "out", "arg", "its",
})


def _split_identifier(name: str) -> list[str]:
    """Split camelCase/PascalCase/snake_case identifiers into lowercase word tokens."""
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name)
    s = re.sub(r'([a-z\d])([A-Z])', r'\1 \2', s)
    return [t.lower() for t in re.split(r'[_\s\d]+', s) if len(t) >= 3]


def _top_tokens(words: list[str], n: int = 40) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter(w for w in words if w not in _STOP_WORDS and len(w) >= 3)
    return counts.most_common(n)


def get_code_stats(db_path: Path) -> dict:
    """Return stats dict for a code.db: languages, symbol types, keyword tags, file count, staleness."""
    if not db_path.exists():
        return {}
    db = _open_code(db_path)
    try:
        lang_rows = db.execute(
            "SELECT COALESCE(language, '') AS lang, COUNT(*) AS cnt "
            "FROM code_chunks GROUP BY lang ORDER BY cnt DESC"
        ).fetchall()
        type_rows = db.execute(
            "SELECT COALESCE(type, '') AS typ, COUNT(*) AS cnt "
            "FROM symbols GROUP BY typ ORDER BY cnt DESC"
        ).fetchall()
        total_chunks = db.execute("SELECT COUNT(*) FROM code_chunks").fetchone()[0]
        total_symbols = db.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        file_count = db.execute("SELECT COUNT(DISTINCT rel_path) FROM file_manifest").fetchone()[0]
        max_mtime = db.execute("SELECT MAX(mtime) FROM file_manifest").fetchone()[0]
        symbol_names = [r[0] for r in db.execute(
            "SELECT name FROM symbols WHERE name IS NOT NULL"
        ).fetchall()]
    finally:
        db.close()

    tokens: list[str] = []
    for name in symbol_names:
        tokens.extend(_split_identifier(name))

    return {
        "languages": [(r["lang"] or "unknown", r["cnt"]) for r in lang_rows],
        "symbol_types": [(r["typ"] or "unknown", r["cnt"]) for r in type_rows],
        "total_chunks": total_chunks,
        "total_symbols": total_symbols,
        "file_count": file_count,
        "max_mtime": max_mtime,
        "keyword_tags": _top_tokens(tokens, 40),
    }


def get_docs_stats(db_path: Path) -> dict:
    """Return stats dict for a docs.db: section/doc counts, doc types, keyword tags, staleness."""
    if not db_path.exists():
        return {}
    db = _open_docs(db_path)
    try:
        total_sections = db.execute("SELECT COUNT(*) FROM doc_sections").fetchone()[0]
        total_docs = db.execute("SELECT COUNT(DISTINCT source_path) FROM doc_sections").fetchone()[0]
        type_rows = db.execute(
            "SELECT COALESCE(doc_type, '') AS typ, COUNT(*) AS cnt "
            "FROM doc_sections GROUP BY typ ORDER BY cnt DESC"
        ).fetchall()
        file_count = db.execute("SELECT COUNT(DISTINCT rel_path) FROM file_manifest").fetchone()[0]
        max_mtime = db.execute("SELECT MAX(mtime) FROM file_manifest").fetchone()[0]
        titles = [r[0] for r in db.execute(
            "SELECT title FROM doc_sections WHERE title IS NOT NULL"
        ).fetchall()]
    finally:
        db.close()

    words: list[str] = []
    for title in titles:
        words.extend(w.lower() for w in re.split(r'\W+', title) if len(w) >= 3)

    return {
        "total_sections": total_sections,
        "total_docs": total_docs,
        "doc_types": [(r["typ"] or "unknown", r["cnt"]) for r in type_rows],
        "file_count": file_count,
        "max_mtime": max_mtime,
        "keyword_tags": _top_tokens(words, 40),
    }
