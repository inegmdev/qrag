# qrag — Session Handoff

**Date:** 2026-06-26
**Session summary:** Branch hygiene + C1 fix (MCP exceptions) + C0 feat (multi-language support) + IS1–IS5 backlog items promoted to top priority

---

## Immediate Next Steps (in priority order)

All PRs merged to `main`. Working tree clean.

| PR | What it did |
|----|-------------|
| **#10** (merged) | SSL fallback + clear error message when bundled model is absent |
| **#11** (merged) | MCP server no longer swallows exceptions — `-32700`/`-32603` responses + `mcp_errors.log` |
| **#12** (merged) | 305+ language support via `tree-sitter-language-pack`; build system files indexed as code; `language` column in DB |
| **#15** (merged) | Consumer vs builder dep split; `[build]`/`[build-gpu]`/`[full]` extras; `_ensure_build_deps()` guard in `prepare` |

---

## What Was Done This Session

### Branch cleanup
- Closed PR #9 (`feat/fix-model-loading`) — superseded by #10
- Deleted remote branches: `feat/fix-model-loading`, `claude/upbeat-meitner-qor3ew`

### C1 fix — MCP silent exception swallowing (PR #11)
- `_log_error()` → appends timestamped entries to `~/.qrag/logs/mcp_errors.log`
- `run()` loop: `-32700` on bad JSON, `-32603` on internal errors, exit 0 on interrupt, exit 1 + log on fatal crash
- File: `src/qrag/mcp_server.py`

### C0 feat — Multi-language support (PR #12)
- `tree-sitter-language-pack` replaces `tree-sitter-c` + `tree-sitter-cpp`
- `_EXT_REGISTRY` (40+ extensions) + `_FILENAME_REGISTRY` (CMakeLists.txt, Makefile, Cargo.toml, package.json, go.mod, pom.xml, conanfile.py, …)
- Language-agnostic `chunk_type`: function/class/struct/interface/enum/macro/type_alias/module/constant
- `language` TEXT column in `code_chunks` and `symbols`; auto-migration in `_open_code()`
- `_detect_input_type()` now registry-driven
- Build file chunks: cmake `add_executable/add_library` → `constant`; Makefile targets → `function`; TOML sections → `struct`
- `search_code`, `list_symbols`, `get_symbol` all return `language` field

### GH#13 — Consumer vs builder dep split (PR #15)
- Consumer baseline: `click + sqlite-vec + sentence-transformers`
- Builder extras in `[build]`: `tree-sitter`, `tree-sitter-language-pack`, `pymupdf`, `html2text`, `beautifulsoup4`
- `[build-gpu]`: `torch>=2.0`; `[full]`: both combined
- `_ensure_build_deps()` probes builder modules at `prepare` entry; prints reinstall instructions and exits 1 if missing

### Documentation & prioritization
- IS1–IS5 added as top-of-Critical in `docs/BACKLOG.md` (user-declared highest priority)
- H0 (build-source relationship metadata) added to High tier
- L8 (shebang sniffing) added to Low tier
- `MEMORY.md` fully refreshed
- `CLAUDE.md` updated with GitHub issue sync rule (mandatory on every backlog query)

---

## Immediate Next Steps (in priority order)

1. **IS1** — Rich TUI: `rich` progress bars + ETA for `qrag prepare` (scan → chunk → embed → store stages)
2. **IS2** — Post-prepare report: `prepare-report.txt` with per-file language/chunks/time + skipped files
3. **IS4** — Rich doc metadata: doc name, revision, status, full section hierarchy, page number in `doc_sections`
4. **IS5** — Rich code metadata: parent block name, call depth, chunk index in `code_chunks`
5. **IS3** — Multi-database fan-out search (benchmark 100 DB scenario first)
6. **C2** — Fix `db_path`/`ddb_path` None crash in code-only or docs-only `prepare`
7. **C3** — Close DB connections on exception

---

## Key Files for Next Session

| File | Why it matters |
|------|---------------|
| `src/qrag/chunker.py` | Full rewrite this session — understand `_EXT_REGISTRY`, `_FILENAME_REGISTRY`, `_Rule`, `_LangConfig` |
| `src/qrag/database.py` | `_open_code()` migration wrapper; `language` column in all code queries |
| `src/qrag/cli.py` | IS1/IS2 work happens here |
| `src/qrag/doc_parser.py` | IS4 work happens here |
| `src/qrag/mcp_server.py` | IS3 multi-DB fan-out work happens here |
| `docs/BACKLOG.md` | IS1–IS5 at the top — read before starting |

---

## Known Risk for PR #12

`conanfile.txt` is registered with `ts_name="ini"` — if tree-sitter-language-pack doesn't have an `ini` grammar, `_get_cached_parser("ini")` raises `RuntimeError` on first use. Fix: remove `conanfile.txt` from `_FILENAME_REGISTRY` or map it to a plain-text fallback that returns zero chunks gracefully.

---

## Git Conventions

- Always create a feature branch from `main`
- Always open a PR before merging
- Never push directly to `main`
- No `Co-Authored-By` trailers in commit messages
