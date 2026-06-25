# qrag — Session Handoff

**Date:** 2026-06-26
**Session summary:** Branch hygiene + C1 fix (MCP exceptions) + C0 feat (multi-language support)

---

## Open PRs (all need review + merge before new work)

| PR | Branch | What it does |
|----|--------|-------------|
| **#10** | `feat/uv-install-and-error-logging` | SSL fallback + clear error message when bundled model is absent. Your commit (inegm authorship) — the canonical fix. |
| **#11** | `fix/c1-mcp-silent-exception-swallow` | MCP server no longer swallows exceptions silently. `JSONDecodeError` → `-32700`, unhandled exceptions → `-32603` + full trace logged to `~/.qrag/logs/mcp_errors.log`. `KeyboardInterrupt` → clean exit 0. |
| **#12** | `feat/c0-multi-language-support` | **Large change.** 305+ language support via `tree-sitter-language-pack`; build system files (CMakeLists.txt, Makefile, Cargo.toml, etc.) indexed as first-class code; language-agnostic `chunk_type`; `language` column added to DB with auto-migration. |

---

## What Was Done This Session

### Branch cleanup
- Closed PR #9 (`feat/fix-model-loading`) — superseded by #10
- Deleted remote branches: `feat/fix-model-loading`, `claude/upbeat-meitner-qor3ew`
- Opened PR #10 from `feat/uv-install-and-error-logging` as the correct canonical fix

### C1 fix — MCP silent exception swallowing (PR #11)
- Added `_log_error()` helper → appends timestamped entries to `~/.qrag/logs/mcp_errors.log`
- Added `_error_response()` helper for clean JSON-RPC error dicts
- `run()` loop now: responds with `-32700` on bad JSON, `-32603` on internal errors, exits 0 on interrupt, exits 1 + logs on fatal crash
- File: `src/qrag/mcp_server.py`

### C0 feat — Multi-language support (PR #12)
**Files changed:** `pyproject.toml`, `src/qrag/chunker.py` (full rewrite), `src/qrag/database.py`, `src/qrag/cli.py`

Key design choices locked during grill-me session:
- `tree-sitter-language-pack` (single dep) replaces `tree-sitter-c` + `tree-sitter-cpp`
- `_EXT_REGISTRY` maps 40+ extensions → `_LangConfig`; `_FILENAME_REGISTRY` maps exact filenames (CMakeLists.txt, Makefile, Cargo.toml, package.json, go.mod, pom.xml, conanfile.py, …)
- Each `_LangConfig` carries a list of `_Rule` objects: `node_types → chunk_type + extract_name callable`
- `chunk_type` is free-form string (function/class/struct/interface/enum/macro/type_alias/module/constant) — no schema migration needed for future languages
- `language` TEXT column added to `code_chunks` and `symbols`; auto-migration in `_open_code()`
- `_detect_input_type()` in `cli.py` is now registry-driven — no hardcoded `.c/.h/.cpp` lists
- Build system files produce chunks: cmake `add_executable()/add_library()` → `constant` type; Makefile targets → `function`; TOML sections → `struct`; package.json keys → `constant`
- `search_code`, `list_symbols`, `get_symbol` all return `language` field now

### New backlog items added
- **IS1–IS5** (from `docs/ISSUES.md`) promoted to top-of-Critical with user-declared highest priority
- **H0** — build-source relationship metadata (phase 2 of build system support)
- **L8** — shebang/content sniffing for extensionless scripts

---

## Immediate Next Steps (in priority order)

1. **Merge PRs #10, #11, #12** after review/testing
2. **IS1** — Rich TUI: add `rich` progress bars + ETA to `qrag prepare` (chunking, embedding, DB write stages)
3. **IS2** — Post-prepare report: write `prepare-report.txt` per-file language/chunks/time + summary
4. **IS4** — Rich doc metadata: doc name, revision, status, section hierarchy, page number in `doc_sections`
5. **IS5** — Rich code metadata: parent block name, call depth, chunk index in `code_chunks`
6. **IS3** — Multi-database fan-out search (benchmark 100 DB scenario first)
7. **C2** — Fix `db_path`/`ddb_path` None crash in code-only or docs-only `prepare`
8. **C3** — Close DB connections on exception (file descriptor exhaustion)

---

## Key Files for Next Session

| File | Why it matters |
|------|---------------|
| `src/qrag/chunker.py` | Full rewrite this session — understand `_EXT_REGISTRY`, `_FILENAME_REGISTRY`, `_Rule`, `_LangConfig` before touching |
| `src/qrag/database.py` | `_open_code()` migration wrapper; `language` column now in all code queries |
| `src/qrag/cli.py` | `_detect_input_type()` now registry-driven; IS1/IS2 work happens here |
| `src/qrag/doc_parser.py` | IS4 work happens here — enrich extracted metadata |
| `src/qrag/mcp_server.py` | C1 fixed; IS3 multi-DB fan-out work happens here |
| `docs/BACKLOG.md` | IS1–IS5 are at the top — read before starting |
| `docs/ISSUES.md` | Source of IS1–IS5; keep in sync with BACKLOG.md |

---

## Testing Notes for PR #12

PR #12 is untested — user will test locally. Known risks:
- `tree-sitter-language-pack` grammar names may differ from what `chunker.py` passes to `get_parser()`. If a grammar lookup fails, `_get_cached_parser()` raises `RuntimeError` with a clear message. Per-language node type names may not match exactly — this degrades to zero chunks for that file (no crash).
- The `language` column auto-migration uses `ALTER TABLE ADD COLUMN` wrapped in try/except — safe for existing DBs.
- `conanfile.txt` is registered with `ts_name="ini"` which may not exist in tree-sitter-language-pack — will raise on first use. Consider falling back to raw text chunking for ini files.

---

## Git Conventions (unchanged)

- Always create a feature branch from `main`
- Always open a PR before merging
- Never push directly to `main`
- No `Co-Authored-By` trailers in commit messages
