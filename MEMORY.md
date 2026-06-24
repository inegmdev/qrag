# qrag — Project Memory

> **How to use this file:** Read it at the start of every new Claude session. Update it before ending any session where significant design decisions, context, or accumulated discussion happened. It is intentionally dense — prefer references to full docs over inline prose.

---

## What is qrag?

**qrag** (née *raghub*) is a Python CLI + MCP server that builds semantic RAG databases from C/C++ codebases and technical documentation (PDFs, HTML). It is designed for embedded-systems teams working with large vendor SDKs (e.g. TI RTOS) and technical reference manuals (TRMs).

**Core value proposition:** One team member prepares the index once (parsing + embedding); the whole team downloads pre-built SQLite databases and gets instant semantic + structural code search inside their AI agent (Claude, Gemini CLI).

**Version:** `0.2.0` (as of 2026-06-24)  
**PyPI status:** Not yet published — install via `uv tool install git+https://github.com/inegmdev/qrag.git@main`

---

## Product Features

| Feature | Status |
|---------|--------|
| C/C++ parsing via Tree-sitter (functions, structs, macros) | ✅ Implemented |
| PDF/HTML doc parsing + section chunking | ✅ Implemented |
| Local embeddings via `all-MiniLM-L6-v2` (384-dim, Sentence-Transformers) | ✅ Implemented |
| SQLite + sqlite-vec for vector storage/search | ✅ Implemented |
| MCP server (JSON-RPC 2.0 over stdio) exposing 4 tools | ✅ Implemented |
| `qrag prepare` — build `code.db` + `docs.db` | ✅ Implemented |
| `qrag hub push/download/list` — GitHub Releases distribution | ✅ Implemented |
| `qrag ai setup` — auto-install MCP config for Claude/Gemini | ✅ Implemented |
| `qrag search code/docs/symbol` — CLI search | ✅ Implemented |
| Automatic error log on failure (`~/.qrag/logs/`) | ✅ PR #7 |
| `uv` as primary install method | ✅ PR #7 |
| `--version` with changelog | ✅ PR #7 |
| PyPI publish | ❌ Not done (see issue `007`) |
| GPU embedding / multicore chunking | ❌ Not done (see issue `008`) |
| Incremental database update | ❌ Not done (see issue `009`) |
| Watch folder / live update | ❌ Not done (see issue `010`) |
| Multi-model embedding | ❌ Not done (see issue `011`) |

---

## MCP Tools (exposed to AI agents)

| Tool | Description |
|------|-------------|
| `search_code(query)` | Semantic search over code chunks; returns symbol, file, line range, snippet, score |
| `search_docs(query)` | Semantic search over doc sections; returns title, content, page range, feature tags, score |
| `get_symbol_definition(symbol)` | Exact definition lookup by name |
| `list_symbols(pattern="")` | List all indexed symbols, optionally filtered |

---

## Architecture

```
PREPARATION (runs once per SDK/docs update):
  Source (.c/.h/.cpp) + Docs (.pdf/.html)
    → chunker.py (Tree-sitter / BeautifulSoup+PyMuPDF)
    → embedder.py (all-MiniLM-L6-v2, 384-dim)
    → database.py (SQLite + sqlite-vec)
    → ~/.qrag/<version>/code.db + docs.db
    → github_distribution.py → GitHub Releases

TEAM USAGE:
  qrag hub download <version>
  qrag ai setup --ai=claude|gemini
  → AI agent calls MCP tools → mcp_server.py → database.py
```

**Key source files:**

| File | Role |
|------|------|
| `src/qrag/cli.py` | Click CLI; `main()` entry point wraps `cli()` for error logging |
| `src/qrag/mcp_server.py` | JSON-RPC 2.0 MCP server over stdio |
| `src/qrag/database.py` | SQLite + sqlite-vec; `search_code`, `search_docs`, `get_symbol`, `list_symbols` |
| `src/qrag/embedder.py` | Sentence-Transformers wrapper; model hardcoded to `all-MiniLM-L6-v2` |
| `src/qrag/chunker.py` | Tree-sitter C/C++ → functions/structs/macros; large functions sub-chunked |
| `src/qrag/doc_parser.py` | PDF (PyMuPDF) + HTML (BeautifulSoup) → doc sections |
| `src/qrag/config.py` | `~/.qrag/config.json` load/save |
| `src/qrag/github_distribution.py` | GitHub Releases API for push/download/list |

**User data layout:**
```
~/.qrag/
├── config.json          # { repo_url, active_version, cache_dir }
├── logs/                # Auto-written on any non-zero exit (since v0.2.0)
├── <version>/
│   ├── code.db
│   ├── docs.db
│   ├── config.json      # version metadata
│   └── manifest.json
```

---

## Known Issues (Backlog)

Full list: [`docs/BACKLOG.md`](docs/BACKLOG.md). Priority order for new sessions:

| ID | File | Severity | Summary |
|----|------|----------|---------|
| C1 | `mcp_server.py:226-229` | Critical | All exceptions silently swallowed — server appears running but isn't |
| C2 | `cli.py:543,547` | Critical | `db_path`/`ddb_path` can be `None` in code-only or docs-only prepare → `TypeError` |
| C3 | `database.py` (multiple) | Critical | DB connections not closed on exception → fd exhaustion |
| H1 | `database.py:249,378` | High | `feature_tags` CSV with commas in tag values → silent misalignment |
| H2 | `database.py:350-422` | High | No embedding-dim validation → garbage results if model changes |
| H3 | `cli.py:436-440` | High | `prepare` exits 0 even when producers error |
| H4 | `cli.py:525` | High | Producer thread death without sentinel → infinite hang |
| H5 | `chunker.py:50` | High | Sub-chunk name collision with real symbol names |
| H6 | `config.py:29-31` | High | `JSONDecodeError` on malformed config breaks all commands |
| M1–M6, L1–L7 | various | Medium/Low | See `docs/BACKLOG.md` |

---

## Git & PR State (as of 2026-06-24)

| Branch | State |
|--------|-------|
| `main` | Clean; has README restructure + full backlog audit |
| `feat/uv-install-and-error-logging` | **PR #8 open** — error logging, uv install, v0.2.0, battery-included model (M7), graceful exceptions (H7) |
| `claude/upbeat-meitner-qor3ew` | Session branch (superseded by PR #8) |

**PR #7** adds: automatic `~/.qrag/logs/` error logging, `main()` entry point, `uv` install docs, v0.2.0 bump, `--version` changelog. Awaiting merge.

---

## Design Decisions (Accumulated)

- **SQLite + sqlite-vec** chosen over Chroma/Pinecone for zero-dependency single-file distribution
- **`all-MiniLM-L6-v2`** (384-dim) chosen for local/free/fast; no API cost; good for technical code
- **Function-level chunking** — Tree-sitter identifies exact boundaries; large functions auto-split with overlap
- **Section-level doc chunking** — preserves heading hierarchy and page references (important for TRM navigation)
- **Single active version** — simplifies MCP tool signatures; version is implicit context
- **GitHub Releases** for database distribution — no custom infra needed; `gh` CLI for auth
- **`uv tool install`** as primary install method — isolated envs, no system-package conflicts
- Entry point changed from `qrag.cli:cli` → `qrag.cli:main` in v0.2.0 to enable error-log wrapping

---

## Issue Tracker

Structured issues live in `issues/` directory:

| File | Topic |
|------|-------|
| `issues/001-scaffold-search-code-e2e.md` | E2E search scaffold |
| `issues/002-prepare-sdk-tree-sitter.md` | SDK tree-sitter prep |
| `issues/003-prepare-docs-pdf-html.md` | Docs PDF/HTML prep |
| `issues/004-database-distribution-github.md` | GitHub distribution |
| `issues/005-mcp-server-install.md` | MCP server install |
| `issues/006-polish-tests-docs.md` | Test/docs polish |
| `issues/007-publish-pypi-npm.md` | PyPI/npm publish |
| `issues/008-gpu-embedding-multicore-chunking.md` | GPU + multicore |
| `issues/009-incremental-database-update.md` | Incremental update |
| `issues/010-watch-folder-live-update.md` | Watch folder |
| `issues/011-multi-model-embedding.md` | Multi-model embedding |

Full PRD: [`docs/PRD.md`](docs/PRD.md)

---

## How to Start a New Session

1. Read this file (`MEMORY.md`)
2. Read [`docs/BACKLOG.md`](docs/BACKLOG.md) for current issue state
3. Check `git log --oneline -10` and open PRs for recent changes
4. Work on highest-severity unresolved backlog items unless user directs otherwise
5. Before ending: update `docs/BACKLOG.md` checkboxes and add any new items discovered; update this file if design decisions, architecture, or product scope changed
