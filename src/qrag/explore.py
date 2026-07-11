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
import shutil
import sqlite3
from abc import ABC, abstractmethod
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


def delete_local(name: str) -> bool:
    """Delete a local version directory and drop it from active_versions.

    Returns True if the version had been active. Rendering, summaries, and
    confirmation are the caller's responsibility.
    """
    from .config import remove_active_version

    version_dir = CACHE_DIR / name
    if version_dir.exists():
        shutil.rmtree(version_dir)
    return remove_active_version(name)


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


# ===========================================================================
# Remote backends
# ===========================================================================
#
# Extensibility contract: a backend is any RemoteBackend subclass registered
# with @register_backend("<type>"). Adding a new remote is one subclass + the
# decorator — nothing else in the codebase changes. The config `type` field of
# each entry in ~/.qrag/config.json:remotes selects the class. Entry-point
# plugin discovery can be layered on later without touching this contract.

@dataclass
class RemoteVersion:
    """A version available on a remote (one row on the remote side of a list)."""
    name: str
    remote: str
    size_bytes: int | None = None
    updated_at: datetime.datetime | None = None
    url: str = ""


@dataclass
class ExploreRow:
    """A version merged across local cache and a remote, keyed by name."""
    name: str
    local: VersionInfo | None = None
    remote: RemoteVersion | None = None

    @property
    def location(self) -> str:
        if self.local and self.remote:
            return "local+remote"
        return "local" if self.local else "remote"


class RemoteError(RuntimeError):
    """Raised for any remote-side failure (auth, network, unknown remote)."""


class RemoteBackend(ABC):
    """Uniform contract every distribution backend implements.

    Transport is a backend detail (subprocess CLI, SDK, …). Each backend
    lazily detects its tooling and raises RemoteError with an actionable
    message only when actually used, so unused remotes cost nothing.
    """

    type: str = ""
    can_push: bool = True

    def __init__(self, url: str, name: str) -> None:
        self.url = url
        self.name = name

    @abstractmethod
    def check_auth(self) -> None:
        """Raise RemoteError if the caller is not authenticated (pre-flight)."""

    @abstractmethod
    def list_versions(self) -> list[RemoteVersion]:
        ...

    @abstractmethod
    def download(self, version: str, dest_dir: Path) -> None:
        """Fetch VERSION into dest_dir/<version>/ (with checksum verification)."""

    @abstractmethod
    def push(self, version: str, src_dir: Path, *, force: bool = False) -> None:
        ...

    @abstractmethod
    def delete_remote(self, version: str) -> None:
        """Remove a published VERSION. The CLI guards this behind a confirmation."""


REGISTRY: dict[str, type[RemoteBackend]] = {}


def register_backend(type_name: str):
    """Class decorator that registers a RemoteBackend under a config `type`."""
    def _decorator(cls: type[RemoteBackend]) -> type[RemoteBackend]:
        cls.type = type_name
        REGISTRY[type_name] = cls
        return cls
    return _decorator


def _parse_dt(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@register_backend("github")
class GitHubBackend(RemoteBackend):
    """GitHub Releases backend — wraps github_distribution.py (the gh CLI)."""

    can_push = True

    def check_auth(self) -> None:
        from .github_distribution import _get_github_token
        if not _get_github_token():
            raise RemoteError(
                "No GitHub authentication. Set GITHUB_TOKEN or run 'gh auth login'."
            )

    def list_versions(self) -> list[RemoteVersion]:
        from .github_distribution import fetch_releases
        try:
            releases = fetch_releases(self.url)
        except RuntimeError as e:
            raise RemoteError(str(e)) from e
        versions = []
        for rel in releases:
            tag = rel.get("tagName") or rel.get("name") or ""
            if not tag:
                continue
            versions.append(RemoteVersion(
                name=tag,
                remote=self.name,
                updated_at=_parse_dt(rel.get("publishedAt")),
                url=f"{self.url.rstrip('/')}/releases/tag/{tag}",
            ))
        return versions

    def download(self, version: str, dest_dir: Path) -> None:
        from .github_distribution import download_database
        download_database(self.url, version, dest_dir)

    def push(self, version: str, src_dir: Path, *, force: bool = False) -> None:
        from .github_distribution import push_to_github
        push_to_github(self.url, version, src_dir, force=force)

    def delete_remote(self, version: str) -> None:
        from .github_distribution import delete_release
        delete_release(self.url, version)


# ---------------------------------------------------------------------------
# Remote resolution & operations
# ---------------------------------------------------------------------------

def resolve_remote(name: str | None = None) -> tuple[str, dict]:
    """Resolve a remote to (name, {type, url}).

    With a name: that named remote (error if unknown). Without: the configured
    default remote, else a synthesized github default from the legacy repo_url /
    QRAG_GITHUB_URL env for backward compatibility.
    """
    from .config import default_remote, get_remote, repo_url

    if name:
        cfg = get_remote(name)
        if cfg is None:
            raise RemoteError(f"No remote named '{name}' is configured.")
        return name, cfg

    dr = default_remote()
    if dr is not None:
        return dr

    url = repo_url()
    if url:
        return "default", {"type": "github", "url": url}

    raise RemoteError(
        "No remote configured. Add one with:\n"
        "  qrag explore add-remote <name> --type github <url>"
    )


def get_backend(name: str | None = None) -> RemoteBackend:
    """Instantiate the RemoteBackend for a (possibly default) remote name."""
    remote_name, cfg = resolve_remote(name)
    remote_type = cfg.get("type", "github")
    cls = REGISTRY.get(remote_type)
    if cls is None:
        raise RemoteError(
            f"Unknown remote type '{remote_type}' for remote '{remote_name}'. "
            f"Known types: {', '.join(sorted(REGISTRY)) or '(none)'}."
        )
    return cls(url=cfg["url"], name=remote_name)


def remote_versions(name: str | None = None) -> list[RemoteVersion]:
    """List versions on a remote (auth-checked). Raises RemoteError on failure."""
    backend = get_backend(name)
    backend.check_auth()
    return backend.list_versions()


def merge_versions(
    locals_: list[VersionInfo], remotes: list[RemoteVersion]
) -> list[ExploreRow]:
    """Merge local and remote versions by name into a unified, sorted listing."""
    rows: dict[str, ExploreRow] = {}
    for v in locals_:
        rows[v.name] = ExploreRow(name=v.name, local=v)
    for r in remotes:
        rows.setdefault(r.name, ExploreRow(name=r.name)).remote = r
    return [rows[name] for name in sorted(rows)]


def write_origin(version: str, remote_name: str) -> None:
    """Record which remote a version was downloaded from, in its config.json."""
    cfg_path = CACHE_DIR / version / "config.json"
    data: dict = {}
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data["origin_remote"] = remote_name
    data["origin_version"] = version
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(data, indent=2))
