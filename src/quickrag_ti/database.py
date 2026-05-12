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
