# qrag — Session Handoff

**Date:** 2026-06-24  
**Branch in progress:** `feat/uv-install-and-error-logging`  
**Open PR:** [#7 — feat: error log on failure + uv as primary install + v0.2.0](https://github.com/inegmdev/qrag/pull/7)

---

## What Was Done This Session

### 1. README & DEVELOPMENT.md restructured (merged to main via PR #6 / now in PR #7)
- `README.md` rewritten user-first: End Users → Database Preparers → link to DEVELOPMENT.md
- `DEVELOPMENT.md` created to hold all developer-facing content (was inline in README)

### 2. Codebase audit → `docs/BACKLOG.md` (on main)
- Full audit conducted across all source files
- 25 issues logged across Critical / High / Medium / Low tiers
- `CLAUDE.md` updated to instruct every new session to read `docs/BACKLOG.md` first

### 3. Automatic error log on failure (`feat/uv-install-and-error-logging`, PR #7)
- Any command that exits non-zero or crashes writes `~/.qrag/logs/qrag-YYYYMMDD-HHMMSS.log`
- Log contains: qrag version, Python version, platform, full argv, all internal log records, exception traceback
- stderr message prints the log path and links to `github.com/inegmdev/qrag/issues/new`
- New `main()` entry point wraps `cli(standalone_mode=False)` to intercept all exit paths
- Producer errors in `prepare` now exit non-zero (previously silently succeeded)
- `pyproject.toml` entry point changed from `qrag.cli:cli` → `qrag.cli:main`

### 4. Version bumped to 0.2.0 (PR #7)
- `src/qrag/__init__.py` and `pyproject.toml` updated
- `--version` now prints a changelog via `_CHANGELOG` constant in `cli.py`

### 5. uv as primary install method (PR #7)
- `README.md` now leads with `uv tool install git+...` for both end users and database preparers
- `DEVELOPMENT.md` now leads with `uv sync --extra dev`, with pip as explicit fallback
- All CLI test commands in DEVELOPMENT.md use `uv run qrag ...`

---

## Current State

| Item | Status |
|------|--------|
| `main` branch | Clean; has audit backlog + README restructure |
| PR #7 | Open, awaiting review & merge |
| Old branch `claude/upbeat-meitner-qor3ew` | Superseded by PR #7; can be deleted |
| Backlog items | All 25 items still open — none fixed yet |

---

## Immediate Next Steps

1. **Merge PR #7** after review
2. **Fix C2** (`cli.py`) — `db_path`/`ddb_path` can be `None` in code-only or docs-only `prepare` runs → `TypeError` crash (highest-impact, easiest fix)
3. **Fix C1** (`mcp_server.py:226-229`) — silent exception swallowing in MCP server event loop
4. **Fix C3** (`database.py`) — DB connections not closed on exception → file descriptor exhaustion
5. **Fix H6** (`config.py:29-31`) — uncaught `JSONDecodeError` on malformed config breaks all commands

See [`docs/BACKLOG.md`](BACKLOG.md) for the full prioritized list.

---

## Key Files

| File | Purpose |
|------|---------|
| `src/qrag/cli.py` | Main CLI; `main()` entry point, `_BufferingHandler`, `_write_error_log()` |
| `src/qrag/mcp_server.py` | JSON-RPC MCP server (C1 lives here) |
| `src/qrag/database.py` | SQLite + sqlite-vec operations (C3, H1, H2 live here) |
| `src/qrag/config.py` | Config load/save (H6 lives here) |
| `src/qrag/chunker.py` | Tree-sitter code parsing (H5, M2 live here) |
| `docs/BACKLOG.md` | Authoritative issue list — update checkboxes as items are fixed |
| `CLAUDE.md` | Session instructions — read at start of every session |

---

## Git Workflow Established This Session

- **Always create a new feature branch** from `main` (never reuse `claude/*` branches)
- **Always open a PR** for review before merging
- **Never push directly to `main`** without user confirmation
- Commit messages: no `Co-Authored-By` or `Claude-Session` trailers (per `CLAUDE.md`)

---

## Suggested Skills

For the next session, the following skills are relevant:

- **`/diagnosing-bugs`** — use when investigating C1 (silent MCP exceptions) or C3 (unclosed DB connections)
- **`/tdd`** — use when fixing C2/C3/H6; all fixes should be test-driven given the risk of regression
- **`/code-review`** — run on the diff before pushing any fix to catch secondary issues
