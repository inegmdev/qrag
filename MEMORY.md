# qrag — Project Memory

> **How to use this file:** Read it at the start of every new Claude session. Update it before ending any session where significant design decisions, context, or accumulated discussion happened. It is intentionally dense — prefer references to full docs over inline prose.

---

## What is qrag?

**qrag** (née *raghub*) is a Python CLI + MCP server that builds semantic RAG databases from source code (any language) and technical documentation (PDFs, HTML). It is designed for embedded-systems teams and software teams working with large vendor SDKs, TRMs, and multi-language codebases.

**Core value proposition:** One team member prepares the index once (parsing + embedding); the whole team downloads pre-built SQLite databases and gets instant semantic + structural code/doc search inside their AI agent (Claude, Gemini CLI).

**Version:** `0.2.0` (as of 2026-06-24)
**Install:** `uv tool install git+https://github.com/inegmdev/qrag.git@main`

---

## Product Features

| Feature | Status |
|---------|--------|
| Multi-language parsing: C, C++, Rust, Python, Go, JS, TS, Java, C#, Ruby, Swift, Kotlin, Scala, Lua, PHP, Bash, Zig, Elixir, Haskell, OCaml, Erlang, Dart, R, Fortran, Verilog, VHDL + more | ✅ PR #12 |
| Build system files indexed as first-class code (CMakeLists.txt, Makefile, Cargo.toml, package.json, go.mod, pom.xml, conanfile.py, *.cmake, *.gradle, *.toml) | ✅ PR #12 |
| Language-agnostic `chunk_type` (function/class/struct/interface/enum/macro/type_alias/module/constant) | ✅ PR #12 |
| `language` column in `code_chunks` + `symbols`; returned in all search/list results | ✅ PR #12 |
| PDF/HTML doc parsing + section chunking | ✅ Implemented |
| Local embeddings via `all-MiniLM-L6-v2` (384-dim, bundled in wheel) | ✅ PR #8 |
| SQLite + sqlite-vec for vector storage/search | ✅ Implemented |
| MCP server (JSON-RPC 2.0 over stdio) exposing 4 tools | ✅ Implemented |
| MCP server exceptions surface as JSON-RPC errors; full trace logged to `~/.qrag/logs/mcp_errors.log` | ✅ PR #11 |
| `qrag prepare` — build `code.db` + `docs.db` | ✅ Implemented |
| `qrag hub push/download/list` — GitHub Releases distribution | ✅ Implemented |
| `qrag ai setup` — auto-install MCP config for Claude/Gemini | ✅ Implemented |
| `qrag search code/docs/symbol` — CLI search | ✅ Implemented |
| Automatic error log on failure (`~/.qrag/logs/`) | ✅ PR #8 |
| `uv` as primary install method | ✅ PR #8 |
| Rich TUI with progress bars + ETA | ❌ IS1 — top priority |
| Post-prepare audit report file | ❌ IS2 — top priority |
| Multi-database search (fan-out across N active DBs) | ❌ IS3 — top priority |
| Rich doc metadata (name, revision, status, page, section hierarchy) | ❌ IS4 — top priority |
| Rich code metadata (parent block, call depth, chunk index within parent) | ❌ IS5 — top priority |
| PyPI publish | ❌ Not done |
| GPU embedding / multicore chunking | ❌ Not done |

---

## MCP Tools (exposed to AI agents)

| Tool | Description | Returns |
|------|-------------|---------|
| `search_code(query)` | Semantic search over code chunks | symbol, file, line range, snippet, type, **language**, score |
| `search_docs(query)` | Semantic search over doc sections | title, content, page range, feature tags, doc_type, score |
| `get_symbol_definition(symbol)` | Exact definition lookup by name | full code text, file, line range, type, **language** |
| `list_symbols(pattern="")` | List all indexed symbols | name, type, **language**, file, line |

---

## Architecture

```
PREPARATION (runs once per SDK/docs update):
  Source files (C/C++/Rust/Python/Go/…) + Build files (CMakeLists.txt/Cargo.toml/…) + Docs (.pdf/.html)
    → chunker.py (tree-sitter-language-pack, 305+ grammars / BeautifulSoup+PyMuPDF)
    → embedder.py (all-MiniLM-L6-v2, 384-dim, bundled in wheel)
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
| `src/qrag/mcp_server.py` | JSON-RPC 2.0 MCP server over stdio; errors now surface + logged |
| `src/qrag/database.py` | SQLite + sqlite-vec; code/doc search, symbol lookup; `language` column |
| `src/qrag/embedder.py` | Sentence-Transformers wrapper; bundled `all-MiniLM-L6-v2` |
| `src/qrag/chunker.py` | Registry-driven multi-language parser (305+ grammars via tree-sitter-language-pack); `_EXT_REGISTRY` + `_FILENAME_REGISTRY` |
| `src/qrag/doc_parser.py` | PDF (PyMuPDF) + HTML (BeautifulSoup) → doc sections |
| `src/qrag/config.py` | `~/.qrag/config.json` load/save |
| `src/qrag/github_distribution.py` | GitHub Releases API for push/download/list |

**User data layout:**
```
~/.qrag/
├── config.json          # { repo_url, active_version, cache_dir }
├── logs/                # qrag-YYYYMMDD-HHMMSS.log on any failure; mcp_errors.log for MCP
├── <version>/
│   ├── code.db          # code_chunks (language col), symbols (language col), vec_code
│   ├── docs.db          # doc_sections, vec_docs
│   └── manifest.json
```

---

## Backlog (Top Open Items)

Full authoritative list: [`docs/BACKLOG.md`](docs/BACKLOG.md). **IS1–IS5 are user-declared top priorities.**

| ID | Severity | Summary |
|----|----------|---------|
| **IS1** | Critical | Ugly TUI — add rich progress bars + ETA to `prepare` and all long-running commands |
| **IS2** | Critical | No post-prepare report — write `prepare-report.txt` with per-file language, chunks, time |
| **IS3** | Critical | Single active DB only — implement multi-DB fan-out search |
| **IS4** | Critical | Doc chunks missing rich metadata (doc name, revision, status, section hierarchy, page) |
| **IS5** | Critical | Code chunks missing rich metadata (parent block, call depth, chunk index) |
| **C2** | Critical | `db_path`/`ddb_path` can be `None` in code-only or docs-only `prepare` → `TypeError` |
| **C3** | Critical | DB connections not closed on exception → fd exhaustion |
| **H0** | High | Build-source relationship metadata (link cmake targets to their source files) |
| **H1–H6** | High | See `docs/BACKLOG.md` |
| **M1–M6** | Medium | See `docs/BACKLOG.md` |
| **L1–L8** | Low | See `docs/BACKLOG.md` |

---

## Git & PR State (as of 2026-06-26)

| Branch | PR | State |
|--------|----|-------|
| `main` | — | Clean; all merged PRs landed here |
| `feat/uv-install-and-error-logging` | #10 | Open — SSL fallback fix for model loading |
| `fix/c1-mcp-silent-exception-swallow` | #11 | Open — MCP exception surfacing + logging |
| `feat/c0-multi-language-support` | #12 | Open — 305+ language support via tree-sitter-language-pack |

**Merged this cycle:** PR #8 (v0.2.0, error log, bundled model, graceful exceptions)
**Deleted branches:** `feat/fix-model-loading` (superseded by #10), `claude/upbeat-meitner-qor3ew` (superseded by #8)

---

## Design Decisions (Accumulated)

- **SQLite + sqlite-vec** chosen over Chroma/Pinecone for zero-dependency single-file distribution
- **`all-MiniLM-L6-v2`** (384-dim) chosen for local/free/fast; bundled in wheel (no HuggingFace runtime call)
- **`tree-sitter-language-pack`** (single dep, 305+ grammars) replaced individual `tree-sitter-c/cpp` packages — clean path to full language coverage
- **Build system files indexed as code** — CMakeLists.txt, Makefile, Cargo.toml etc. are first-class code chunks, not filtered out; build metadata (targets, features, variants) must be searchable
- **Language-agnostic chunk_type** — free-form string (function/class/struct/…) so new languages never require a schema migration
- **`language` column** in `code_chunks` and `symbols` — AI agent now knows whether a result is from a Rust file, a CMake file, etc.
- **Function-level chunking** — tree-sitter identifies exact boundaries; large symbols auto-split with overlap
- **Section-level doc chunking** — preserves heading hierarchy and page references (important for TRM navigation)
- **Single active version** (for now) — simplifies MCP tool signatures; IS3 will lift this to multi-DB fan-out
- **GitHub Releases** for database distribution — no custom infra needed
- **`uv tool install`** as primary install method — isolated envs, no system-package conflicts
- Entry point: `qrag.cli:main` (wraps `cli()` for error-log writing on non-zero exit since v0.2.0)
- MCP server errors must never be silently dropped — they surface as JSON-RPC error responses AND are logged to `mcp_errors.log`

---

## How to Start a New Session

1. Read this file (`MEMORY.md`)
2. Read [`docs/BACKLOG.md`](docs/BACKLOG.md) — **IS1–IS5 are top priority**
3. Check `git log --oneline -10` and open PRs (#10, #11, #12) for recent changes
4. Work on IS1 → IS2 → IS3 → IS4 → IS5 → C2 → C3 unless user directs otherwise
5. Before ending: update `docs/BACKLOG.md` checkboxes, update this file if architecture/scope changed, update `docs/HANDOFF.md`
