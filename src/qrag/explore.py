"""Local qrag database exploration — the data layer behind `qrag explore`.

Pure, read-only summaries of the databases under ``~/.qrag/<version>/``. This
module never touches the network and never loads the sqlite-vec extension — it
only reads the plain relational tables (``code_chunks``, ``symbols``,
``doc_sections``). Rendering lives in ``cli.py``; the interactive browser (#46)
and diff (#47) will reuse these same functions.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .config import CACHE_DIR, load_global


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class LangCount:
    """A single language and the number of code chunks written in it."""
    language: str
    chunks: int


@dataclass
class VersionInfo:
    """One row of ``qrag explore list``."""
    name: str
    path: Path
    has_code: bool
    has_docs: bool
    size_bytes: int
    built_at: datetime.datetime | None
    active: bool
    symbols: int
    sections: int
    docs: int
    languages: list[LangCount] = field(default_factory=list)  # sorted desc by chunks


@dataclass
class VersionStats:
    """Full payload for ``qrag explore stats VERSION`` (lean panel)."""
    name: str
    path: Path
    active: bool
    has_code: bool
    has_docs: bool
    size_bytes: int
    built_at: datetime.datetime | None
    embedding_model: str
    symbols: int
    code_chunks: int
    languages: list[LangCount]
    symbol_types: list[tuple[str, int]]  # (type, count), sorted desc
    sections: int
    docs: int
    words: int


# ---------------------------------------------------------------------------
# Read-only sqlite helpers
# ---------------------------------------------------------------------------

def _connect_ro(db_path: Path) -> sqlite3.Connection | None:
    """Open a database read-only. Returns None if it is missing or unreadable."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Run a query, returning [] on any error (e.g. a table that doesn't exist)."""
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def _scalar(conn: sqlite3.Connection, sql: str, default: int = 0) -> int:
    rows = _rows(conn, sql)
    if rows and rows[0][0] is not None:
        return rows[0][0]
    return default


# ---------------------------------------------------------------------------
# Version discovery
# ---------------------------------------------------------------------------

def _is_version_dir(p: Path) -> bool:
    """A version dir is any directory holding a code.db or docs.db."""
    return p.is_dir() and ((p / "code.db").exists() or (p / "docs.db").exists())


def local_version_names() -> list[str]:
    """Sorted names of all local database versions under CACHE_DIR."""
    if not CACHE_DIR.exists():
        return []
    return sorted(p.name for p in CACHE_DIR.iterdir() if _is_version_dir(p))


def _built_at(version_dir: Path) -> datetime.datetime | None:
    """Build time inferred from the newest DB file mtime (config.json has no date)."""
    mtimes = [
        (version_dir / name).stat().st_mtime
        for name in ("code.db", "docs.db")
        if (version_dir / name).exists()
    ]
    if not mtimes:
        return None
    return datetime.datetime.fromtimestamp(max(mtimes))


def _size_bytes(version_dir: Path) -> int:
    total = 0
    for name in ("code.db", "docs.db"):
        p = version_dir / name
        if p.exists():
            total += p.stat().st_size
    return total


def _embedding_model(version_dir: Path) -> str:
    cfg = version_dir / "config.json"
    if cfg.exists():
        try:
            with open(cfg) as f:
                return json.load(f).get("embedding_model", "")
        except (json.JSONDecodeError, OSError):
            return ""
    return ""


# ---------------------------------------------------------------------------
# Per-database summaries
# ---------------------------------------------------------------------------

def _code_summary(code_db: Path) -> dict:
    conn = _connect_ro(code_db)
    if conn is None:
        return {"symbols": 0, "chunks": 0, "languages": [], "symbol_types": []}
    try:
        symbols = _scalar(conn, "SELECT COUNT(*) FROM symbols")
        chunks = _scalar(conn, "SELECT COUNT(*) FROM code_chunks")
        languages = [
            LangCount(r["lang"], r["c"])
            for r in _rows(
                conn,
                "SELECT COALESCE(NULLIF(language, ''), 'unknown') AS lang, "
                "COUNT(*) AS c FROM code_chunks GROUP BY lang ORDER BY c DESC",
            )
        ]
        symbol_types = [
            (r["t"], r["c"])
            for r in _rows(
                conn,
                "SELECT COALESCE(NULLIF(type, ''), 'other') AS t, "
                "COUNT(*) AS c FROM symbols GROUP BY t ORDER BY c DESC",
            )
        ]
        return {
            "symbols": symbols,
            "chunks": chunks,
            "languages": languages,
            "symbol_types": symbol_types,
        }
    finally:
        conn.close()


def _docs_summary(docs_db: Path) -> dict:
    conn = _connect_ro(docs_db)
    if conn is None:
        return {"sections": 0, "docs": 0, "words": 0}
    try:
        return {
            "sections": _scalar(conn, "SELECT COUNT(*) FROM doc_sections"),
            "docs": _scalar(conn, "SELECT COUNT(DISTINCT source_path) FROM doc_sections"),
            "words": _scalar(conn, "SELECT COALESCE(SUM(word_count), 0) FROM doc_sections"),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public gather / compute
# ---------------------------------------------------------------------------

def gather_version(name: str) -> VersionInfo:
    version_dir = CACHE_DIR / name
    code_db = version_dir / "code.db"
    docs_db = version_dir / "docs.db"
    active = name in load_global().get("active_versions", [])
    code = _code_summary(code_db)
    docs = _docs_summary(docs_db)
    return VersionInfo(
        name=name,
        path=version_dir,
        has_code=code_db.exists(),
        has_docs=docs_db.exists(),
        size_bytes=_size_bytes(version_dir),
        built_at=_built_at(version_dir),
        active=active,
        symbols=code["symbols"],
        sections=docs["sections"],
        docs=docs["docs"],
        languages=code["languages"],
    )


def gather_local_versions() -> list[VersionInfo]:
    return [gather_version(name) for name in local_version_names()]


def compute_stats(name: str) -> VersionStats:
    """Detailed stats for one version. Raises FileNotFoundError if unknown."""
    version_dir = CACHE_DIR / name
    if not _is_version_dir(version_dir):
        raise FileNotFoundError(name)
    code = _code_summary(version_dir / "code.db")
    docs = _docs_summary(version_dir / "docs.db")
    return VersionStats(
        name=name,
        path=version_dir,
        active=name in load_global().get("active_versions", []),
        has_code=(version_dir / "code.db").exists(),
        has_docs=(version_dir / "docs.db").exists(),
        size_bytes=_size_bytes(version_dir),
        built_at=_built_at(version_dir),
        embedding_model=_embedding_model(version_dir),
        symbols=code["symbols"],
        code_chunks=code["chunks"],
        languages=code["languages"],
        symbol_types=code["symbol_types"],
        sections=docs["sections"],
        docs=docs["docs"],
        words=docs["words"],
    )


# ---------------------------------------------------------------------------
# Formatting helpers (pure — shared by cli.py and the future TUI)
# ---------------------------------------------------------------------------

def lang_percentages(languages: list[LangCount]) -> list[tuple[str, float]]:
    """Convert per-language chunk counts into percentages (sorted desc)."""
    total = sum(lang.chunks for lang in languages)
    if total == 0:
        return []
    return [(lang.language, 100.0 * lang.chunks / total) for lang in languages]


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # unreachable, keeps type checkers happy


def human_age(dt: datetime.datetime | None) -> str:
    if dt is None:
        return "—"
    delta = datetime.datetime.now() - dt
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h ago"
    minutes = delta.seconds // 60
    if minutes >= 1:
        return f"{minutes}m ago"
    return "just now"
