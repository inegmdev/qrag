from __future__ import annotations

import sqlite3
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


def init_code_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = _open(db_path)
    db.executescript(f"""
        CREATE TABLE IF NOT EXISTS code_chunks (
            id          INTEGER PRIMARY KEY,
            symbol_name TEXT,
            file_path   TEXT,
            line_start  INTEGER,
            line_end    INTEGER,
            code_text   TEXT,
            type        TEXT
        );
        CREATE TABLE IF NOT EXISTS symbols (
            id          INTEGER PRIMARY KEY,
            name        TEXT UNIQUE,
            type        TEXT,
            file_path   TEXT,
            line_number INTEGER,
            chunk_id    INTEGER REFERENCES code_chunks(id)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_code USING vec0(
            chunk_id INTEGER,
            embedding float[{EMBEDDING_DIM}] distance_metric=cosine
        );
    """)
    db.commit()
    db.close()


def delete_chunks_for_file(db_path: Path, file_path: str) -> None:
    """Remove all chunks and vectors belonging to a file (for upsert on re-run)."""
    db = _open(db_path)
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
) -> int:
    db = _open(db_path)
    cur = db.execute(
        """
        INSERT INTO code_chunks (symbol_name, file_path, line_start, line_end, code_text, type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (symbol_name, file_path, line_start, line_end, code_text, chunk_type),
    )
    chunk_id = cur.lastrowid

    db.execute(
        "INSERT OR REPLACE INTO symbols (name, type, file_path, line_number, chunk_id) VALUES (?,?,?,?,?)",
        (symbol_name, chunk_type, file_path, line_start, chunk_id),
    )

    db.execute(
        "INSERT INTO vec_code (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, to_blob(embedding)),
    )

    db.commit()
    db.close()
    return chunk_id


def get_symbol(db_path: Path, name: str) -> dict | None:
    db = _open(db_path)
    row = db.execute(
        """
        SELECT c.symbol_name, c.type, c.file_path, c.line_start, c.line_end, c.code_text
        FROM symbols s
        JOIN code_chunks c ON c.id = s.chunk_id
        WHERE s.name = ?
        """,
        (name,),
    ).fetchone()
    db.close()
    if row is None:
        return None
    return dict(row)


def list_symbols(db_path: Path, pattern: str = "", limit: int = 200) -> list[dict[str, Any]]:
    db = _open(db_path)
    if pattern:
        query = """
            SELECT name, type, file_path, line_number
            FROM symbols
            WHERE name LIKE ?
            ORDER BY name
            LIMIT ?
        """
        rows = db.execute(query, (f"%{pattern}%", limit)).fetchall()
    else:
        query = """
            SELECT name, type, file_path, line_number
            FROM symbols
            ORDER BY name
            LIMIT ?
        """
        rows = db.execute(query, (limit,)).fetchall()
    db.close()

    results = []
    for row in rows:
        results.append({
            "name": row["name"],
            "type": row["type"],
            "file": row["file_path"],
            "line": row["line_number"],
        })
    return results


def init_docs_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = _open(db_path)
    db.executescript(f"""
        CREATE TABLE IF NOT EXISTS doc_sections (
            id           INTEGER PRIMARY KEY,
            source_path  TEXT,
            soc_name     TEXT,
            doc_type     TEXT,
            chapter      INTEGER,
            section      INTEGER,
            subsection   TEXT,
            title        TEXT,
            content      TEXT,
            page_range   TEXT,
            feature_tags TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_docs USING vec0(
            section_id INTEGER,
            embedding float[{EMBEDDING_DIM}] distance_metric=cosine
        );
    """)
    db.commit()
    db.close()


def delete_sections_for_source(db_path: Path, source_path: str) -> None:
    """Remove all doc_sections and vectors for a source file (upsert support)."""
    db = _open(db_path)
    rows = db.execute(
        "SELECT id FROM doc_sections WHERE source_path = ?", (source_path,)
    ).fetchall()
    ids = [r["id"] for r in rows]
    if ids:
        placeholders = ",".join("?" * len(ids))
        db.execute(f"DELETE FROM vec_docs WHERE section_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM doc_sections WHERE id IN ({placeholders})", ids)
    db.commit()
    db.close()


def insert_doc_section(
    db_path: Path,
    source_path: str,
    soc_name: str,
    doc_type: str,
    chapter: int,
    section: int,
    subsection: str,
    title: str,
    content: str,
    page_range: str,
    feature_tags: str,
    embedding: list[float],
) -> int:
    db = _open(db_path)
    cur = db.execute(
        """
        INSERT INTO doc_sections
          (source_path, soc_name, doc_type, chapter, section, subsection,
           title, content, page_range, feature_tags)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (source_path, soc_name, doc_type, chapter, section, subsection,
         title, content, page_range, feature_tags),
    )
    section_id = cur.lastrowid
    db.execute(
        "INSERT INTO vec_docs (section_id, embedding) VALUES (?, ?)",
        (section_id, to_blob(embedding)),
    )
    db.commit()
    db.close()
    return section_id


def search_docs(db_path: Path, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    db = _open(db_path)
    rows = db.execute(
        """
        SELECT
            d.chapter, d.section, d.subsection, d.title,
            d.content, d.page_range, d.feature_tags, d.doc_type,
            v.distance
        FROM vec_docs v
        JOIN doc_sections d ON d.id = v.section_id
        WHERE v.embedding MATCH ?
          AND k = ?
        ORDER BY v.distance
        """,
        (to_blob(query_embedding), top_k),
    ).fetchall()
    db.close()

    results = []
    for row in rows:
        similarity = max(0.0, 1.0 - row["distance"])
        tags = row["feature_tags"] or ""
        results.append({
            "chapter": row["chapter"],
            "section": row["section"],
            "title": row["title"],
            "content": row["content"][:400],
            "page_range": row["page_range"],
            "feature_tags": tags.split(",") if tags else [],
            "doc_type": row["doc_type"],
            "similarity_score": round(similarity, 4),
        })
    return results


def search_code(db_path: Path, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    db = _open(db_path)
    rows = db.execute(
        """
        SELECT
            c.symbol_name,
            c.file_path,
            c.line_start,
            c.line_end,
            c.code_text,
            c.type,
            v.distance
        FROM vec_code v
        JOIN code_chunks c ON c.id = v.chunk_id
        WHERE v.embedding MATCH ?
          AND k = ?
        ORDER BY v.distance
        """,
        (to_blob(query_embedding), top_k),
    ).fetchall()
    db.close()

    results = []
    for row in rows:
        # cosine distance in [0,2]; similarity = 1 - distance maps to [-1,1]
        similarity = max(0.0, 1.0 - row["distance"])
        results.append(
            {
                "symbol_name": row["symbol_name"],
                "file_path": row["file_path"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "code_snippet": row["code_text"][:300],
                "type": row["type"],
                "similarity_score": round(similarity, 4),
            }
        )
    return results
