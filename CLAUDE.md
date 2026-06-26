# Claude Code Instructions

---

## Mandatory Session Start Sequence

**Do this before anything else, every session — no exceptions:**

1. Read `MEMORY.md` — product overview, architecture, design decisions, current git/PR state.
2. Read `docs/BACKLOG.md` — full prioritized bug and improvement list with exact file/line references.
3. Read `docs/ARCHITECTURE.md` — all architectural decisions with visualizations.
4. Run `git log --oneline -10` mentally or explicitly to understand recent commits.
5. Unless the user directs otherwise, prefer working on **Critical → High → Medium → Low** backlog items.

---

## What This Project Is

**qrag** is a Python CLI + MCP server that builds semantic RAG databases from C/C++ source code and technical documentation (PDFs, HTML). It is designed for embedded-systems teams working with large vendor SDKs and TRMs.

**Key workflow:**
- A "database preparer" runs `qrag build` once to parse, embed, and store code/docs into SQLite databases.
- The whole team downloads those pre-built databases via `qrag hub download`.
- Each developer runs `qrag ai setup` to wire the MCP server into their AI agent (Claude or Gemini CLI).
- The AI agent then calls four MCP tools: `search_code`, `search_docs`, `get_symbol_definition`, `list_symbols`.

**Version:** `0.2.0`  
**Entry point:** `qrag.cli:main` (wraps `cli()` for automatic error-log writing on failure)  
**Install:** `uv tool install git+https://github.com/inegmdev/qrag.git@main`

---

## Key Source Files

| File | What it does |
|------|--------------|
| `src/qrag/cli.py` | Click CLI; `main()` entry point + `_write_error_log()` on non-zero exit |
| `src/qrag/mcp_server.py` | JSON-RPC 2.0 MCP server over stdio |
| `src/qrag/database.py` | SQLite + sqlite-vec; `search_code`, `search_docs`, `get_symbol`, `list_symbols` |
| `src/qrag/embedder.py` | Sentence-Transformers `all-MiniLM-L6-v2` (384-dim, local) |
| `src/qrag/chunker.py` | Tree-sitter C/C++ → functions/structs/macros; large symbols auto-split |
| `src/qrag/doc_parser.py` | PyMuPDF + BeautifulSoup → doc sections |
| `src/qrag/config.py` | `~/.qrag/config.json` load/save |
| `src/qrag/github_distribution.py` | GitHub Releases push/download/list |

---

## Backlog Rules

- **Read `docs/BACKLOG.md` at session start** — it is the authoritative source of truth for all known bugs and improvements.
- When an item is resolved: mark `[x]` and add a one-line fix note in `docs/BACKLOG.md`.
- When a new issue is discovered: add it to the correct severity tier in `docs/BACKLOG.md` before or alongside the fix.
- Severity order: **Critical → High → Medium → Low**.

### GitHub Issue Sync — MANDATORY when the user asks about the backlog

Whenever the user asks about the backlog, what's next, or what issues exist:

1. Run `gh issue list --state open --limit 50` to fetch all open GitHub issues.
2. For each GitHub issue **not already tracked** in `docs/BACKLOG.md` (match by title or GH issue number):
   - Add it to the appropriate severity tier in `docs/BACKLOG.md`.
   - Use the format: `- [ ] **GH#<N>** — <title>. [GitHub](<url>)`
   - Assign a severity tier based on the issue title/body (default to **High** if unclear).
3. Commit the additions to `docs/BACKLOG.md` with message: `docs: sync GitHub issues to backlog`.
4. Report the sync result to the user (X new issues added, Y already tracked).

### Top Open Issues (as of last update — verify in `docs/BACKLOG.md`)

| ID | File:Line | Summary |
|----|-----------|---------|
| **C2** | `cli.py` | `db_path`/`ddb_path` can be `None` in code-only or docs-only `build` → `TypeError` |
| **C3** | `database.py` (multiple) | DB connections not closed on exception → file descriptor exhaustion |
| **H3** | `cli.py` | `build` exits 0 even when producers error — corrupt DB looks valid |
| **H4** | `cli.py` | Producer thread death without sentinel → `build` hangs forever |
| **H6** | `config.py:29-31` | `JSONDecodeError` on malformed config breaks every qrag command |
| **GH#18** | `cli.py:274-481` | Add Antigravity CLI support to `qrag ai setup` |

---

## Git & PR Conventions

- **Never push directly to `main`** without explicit user confirmation.
- **Always create a feature branch** from `main` for each fix or feature.
- **Open a PR** for review before merging.
- Commit messages: **no** `Co-Authored-By` or `Claude-Session` trailers.
- Active open PR: **#8** (`feat/uv-install-and-error-logging`) — awaiting merge.

## PR Tracking

After opening a PR:

1. Note the PR number and branch in `MEMORY.md` under "Git & PR State".
2. If CI runs are configured, check the result before closing the session.
3. If CI fails: diagnose the failure, fix it on the same branch, push, and recheck.
4. Do not open a new PR or move to the next backlog item while an existing PR has failing CI.
5. Update `MEMORY.md` when a PR is merged or closed.

---

## Architecture Documentation — MANDATORY

**Whenever a design decision is made or an architectural component changes:**

1. Open `docs/ARCHITECTURE.md`.
2. Add or update the relevant section with:
   - A short **Decision** statement and **Why** rationale.
   - A **Mermaid diagram** (` ```mermaid `) visualizing the flow, data layout, or component relationships. Never use ASCII art — always use Mermaid syntax.
   - A **Trade-off** note if applicable.
3. Assign the section an `AD-N` identifier (next available number).
4. Commit the update alongside the code change — never let code and architecture docs drift apart.

---

## End-of-Session Checklist

Before closing any session where meaningful work happened:

1. Mark resolved backlog items `[x]` in `docs/BACKLOG.md`.
2. Add any newly discovered issues to `docs/BACKLOG.md`.
3. Update `MEMORY.md` if: architecture changed, a design decision was made, PR/branch state changed, or product scope shifted.
4. Update `docs/ARCHITECTURE.md` if any architectural decision was made or changed.
5. Commit and push all changes.
