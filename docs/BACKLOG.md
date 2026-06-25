# qrag — Known Issues & Backlog

This file is the authoritative backlog of known bugs, missing features, and optimization opportunities, derived from a full codebase audit. Items are ordered by criticality within each tier.

When starting a new session, review this file and prefer working on higher-severity items first unless the user directs otherwise. When an item is resolved, mark it with `[x]` and note the fix briefly.

---

## Critical — Broken or Data-Loss Risk

- [ ] **C0** `chunker.py`, `pyproject.toml` — Only C and C++ are supported. Extend to all tree-sitter-supported languages so any codebase can be indexed. Work: (1) add grammar packages to `pyproject.toml` (`tree-sitter-rust`, `tree-sitter-javascript`, `tree-sitter-java`, `tree-sitter-python`, `tree-sitter-go`, `tree-sitter-typescript`, etc.); (2) build a `LANGUAGE_MAP` in `chunker.py` keyed by file extension — node-type names differ per grammar (Rust: `function_item`/`struct_item`, JS: `function_declaration`/`class_declaration`); (3) generalise `_extract_chunks()`; (4) update file-extension filter in `cli.py`; (5) add `--languages` flag on `prepare` so users opt-in rather than pulling every grammar into the wheel.

- [x] **C1** `mcp_server.py:226-229` — All exceptions silently swallowed with `continue`. Fixed in PR #11: `JSONDecodeError` → `-32700` response + log; unhandled `Exception` → `-32603` response + full traceback logged to `~/.qrag/logs/mcp_errors.log`; `KeyboardInterrupt`/`SystemExit` → clean exit 0; fatal loop crash → log + exit 1.

- [ ] **C2** `cli.py:543,547` — `db_path`/`ddb_path` can be `None` in code-only or docs-only `prepare` runs, causing a `TypeError` crash. Single-type indexing is a documented use case.

- [ ] **C3** `database.py` (multiple functions) — DB connections opened without `try/finally`. Any exception leaves the connection open; repeated failures exhaust OS file descriptors.

---

## High — Likely User-Facing Failures

- [ ] **H1** `database.py:249,378` — `feature_tags` stored as comma-CSV but split naively. Tags containing commas cause silent misalignment in search results.

- [ ] **H2** `database.py:350-422` — No validation that query embedding dimension matches `EMBEDDING_DIM=384`. A misconfigured model silently returns garbage search results.

- [ ] **H3** `cli.py:436-440` — Producer exceptions are caught and appended to an errors list, but `prepare` still exits with code `0` and reports success. A corrupted or incomplete database looks valid.

- [ ] **H4** `cli.py:525` — If a producer thread dies without emitting a sentinel, `queue.get()` busy-loops indefinitely. The `prepare` command hangs forever with no error.

- [ ] **H5** `chunker.py:50` — Sub-chunk names (`func#0`, `func#1`) can collide with real symbol names. `INSERT OR REPLACE` silently overwrites the correct symbol entry.

- [ ] **H6** `config.py:29-31` — Malformed `~/.qrag/config.json` raises an uncaught `JSONDecodeError`, breaking every qrag command until the file is manually deleted.

- [x] **H7** `cli.py:main()` — Restructured to never re-raise. `KeyboardInterrupt`/`Abort` → "Interrupted." + exit 130. `BaseException` → "Error: <message>" + exit 1. Raw tracebacks no longer reach the terminal; full trace still written to `~/.qrag/logs/`.

---

## Medium — Degraded UX or Performance

- [ ] **M1** `cli.py:466-499` — No progress reporting during embedding of large batches. The tool appears frozen on large codebases.

- [ ] **M2** `chunker.py:31`, `doc_parser.py:31` — Token count uses `str.split()`. Inaccurate for punctuation-heavy code; the 512-token chunk limit is effectively meaningless.

- [ ] **M3** `embedder.py:46-48` — Float16 precision loss on CUDA is not validated or warned. Search results silently differ between CPU and GPU runs.

- [ ] **M4** `cli.py:611-627` — When an input directory contains no supported files, the error message doesn't identify which `-i` path is the problem.

- [ ] **M5** `cli.py:658-718` — "Roots differ" error prevents incremental updates when adding a new source directory. Users must `--force` rebuild the entire database.

- [ ] **M6** `embedder.py:8` — Embedding model hardcoded with no version stored in the database schema. A future model change silently makes all existing databases incompatible.

- [x] **M7** `embedder.py`, `pyproject.toml` — Embedding model bundled inside the wheel via `scripts/download_model.py` + `[tool.setuptools.package-data]`. `_get_model()` loads from `src/qrag/models/all-MiniLM-L6-v2/` and fails hard with a clear English message if missing. No HuggingFace call at runtime.

---

## Low — Nice-to-Have



- [ ] **L1** `cli.py:851-904` — No deduplication when a result appears in both code and docs search output.

- [ ] **L2** `cli.py` — No `--dry-run` mode for `prepare` to preview what would be indexed without building the database.

- [ ] **L3** `cli.py:936`, `database.py:376,417` — Snippets truncated without a `...` indicator; users don't know they're seeing partial content.

- [ ] **L4** `cli.py` — No single-file re-index; one changed file requires re-processing the entire directory.

- [ ] **L5** `github_distribution.py:253` — Checksum validation is skipped when the manifest download fails silently, allowing a corrupted database to be used.

- [ ] **L6** `cli.py:917,951,985` — Error messages reference `qrag mcp active` but the correct command is `qrag ai active`.

- [ ] **L7** `database.py` — No debug-level logging emitted under `--verbose` for database operations; makes slow or failing `prepare` runs hard to diagnose.
