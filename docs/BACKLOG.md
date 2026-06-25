# qrag — Known Issues & Backlog

This file is the authoritative backlog of known bugs, missing features, and optimization opportunities, derived from a full codebase audit. Items are ordered by criticality within each tier.

When starting a new session, review this file and prefer working on higher-severity items first unless the user directs otherwise. When an item is resolved, mark it with `[x]` and note the fix briefly.

---

## Critical — Broken or Data-Loss Risk

> **IS1–IS5 are user-declared top priorities** (from `docs/ISSUES.md`). Work on these before any other open item.

- [ ] **IS1** `cli.py`, `embedder.py` — TUI is plain echo/print with no visual structure. Modernize `qrag prepare` (and all long-running commands) with rich progress bars (per-file chunking, per-batch embedding, per-batch DB write), live ETA, elapsed time display, and a final summary line. Recommended library: `rich` (already a transitive dep via sentence-transformers — check before adding). Each pipeline stage (scan → chunk → embed → store) should have its own progress bar so the user always knows where the bottleneck is.

- [ ] **IS2** `cli.py` — No post-prepare audit report. After `qrag prepare` completes, write a human-readable report to `<output>/prepare-report.txt` (and print a summary to stdout) containing: list of every file processed, its detected language, number of chunks produced, time taken per file; aggregate stats per language; total wall-clock time; list of files skipped (unsupported extension, parse error, zero chunks); DB sizes. This lets the user verify what entered the database and what was silently dropped.

- [ ] **IS3** `database.py`, `mcp_server.py`, `cli.py` — Only one active database at a time. Users need to search across multiple independently-prepared databases (e.g. SDK code + RTOS code + docs from two vendors) without re-preparing a merged DB. Design: (1) `qrag ai active` becomes `qrag ai active <v1> [v2 ...]`; (2) MCP tools fan-out to all active DBs in parallel, merge results, de-duplicate, re-rank by score; (3) benchmark feasibility at 100 DBs × ~4 MB each — sqlite-vec cosine search is O(n) per DB so fan-out latency must be measured and documented.

- [ ] **IS4** `doc_parser.py`, `database.py` — Document chunks are missing critical metadata for LLM citation. Add to each `doc_sections` row: (a) **document name** (filename without path); (b) **document revision** (parsed from cover page / metadata / filename suffix like `_rev3`); (c) **document status** (`draft`/`revised`/`released` — parse from header/footer or filename); (d) **exact page number or range** (already partially present — verify and surface properly); (e) **full section hierarchy** (chapter → section → subsection → paragraph heading, all levels); (f) **word count** of the chunk; (g) **figure/table references** mentioned in the chunk (e.g. "See Table 4-2"). Update DB schema (`doc_sections` table), `doc_parser.py` extraction, `search_docs` return value, and MCP `search_docs` tool output.

- [ ] **IS5** `chunker.py`, `database.py` — Code chunks lack metadata the LLM needs for precise citation and navigation. Add to each `code_chunks` row: (a) **file name** (basename, already in file_path but should be a dedicated column for fast filtering); (b) **line number range** (already present — ensure it surfaces in all tool outputs); (c) **parent block name** (the enclosing function/class/namespace/module that contains this chunk, if any — e.g. a method chunk should know its class name); (d) **call depth** (top-level vs nested); (e) **detected language** (already added in C0 — verify it surfaces in all outputs); (f) **chunk index within parent** (for sub-chunks like `func#0`). Update DB schema, `chunker.py`, `insert_code_chunks_batch`, `search_code` results, and MCP tool output.

- [x] **C0** `chunker.py`, `pyproject.toml`, `database.py`, `cli.py` — Only C and C++ were supported. Fixed in PR #12: replaced individual `tree-sitter-c`/`tree-sitter-cpp` deps with `tree-sitter-language-pack` (305+ grammars); rewrote `chunker.py` with a `_EXT_REGISTRY`/`_FILENAME_REGISTRY`-driven rule engine; chunk_type is now language-agnostic (function/class/struct/interface/enum/macro/type_alias/module/constant); added `language` column to `code_chunks` and `symbols` with auto-migration; `_detect_input_type()` now derives extensions from the registry; build system files (CMakeLists.txt, Makefile, Cargo.toml, package.json, go.mod, pom.xml, conanfile.py, *.cmake, *.gradle, *.toml, etc.) are indexed as first-class code alongside source files.

- [x] **C1** `mcp_server.py:226-229` — All exceptions silently swallowed with `continue`. Fixed in PR #11: `JSONDecodeError` → `-32700` response + log; unhandled `Exception` → `-32603` response + full traceback logged to `~/.qrag/logs/mcp_errors.log`; `KeyboardInterrupt`/`SystemExit` → clean exit 0; fatal loop crash → log + exit 1.

- [ ] **C2** `cli.py:543,547` — `db_path`/`ddb_path` can be `None` in code-only or docs-only `prepare` runs, causing a `TypeError` crash. Single-type indexing is a documented use case.

- [ ] **C3** `database.py` (multiple functions) — DB connections opened without `try/finally`. Any exception leaves the connection open; repeated failures exhaust OS file descriptors.

---

## High — Likely User-Facing Failures

- [ ] **H0** `chunker.py`, `database.py` — Build-source relationship metadata: currently build system files (CMakeLists.txt, Cargo.toml, etc.) are indexed as isolated chunks. Phase 2 should enrich `code_chunks` with relational metadata — e.g. which source files belong to which cmake target/cargo bin/gradle task — so that RAG queries like "what files are compiled into the `my_app` executable?" return structured answers. Work: (1) add a `build_target` TEXT column to `code_chunks`; (2) parse cmake `add_executable`/`add_library` arguments to extract the source file list and back-link those source chunks to the target name; (3) do the same for Cargo `[[bin]]`→`src`, Gradle `sourceSets`, Maven `<module>` etc.; (4) expose `build_target` in `search_code` results so the AI agent can filter by target. Depends on C0.

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

- [ ] **L8** `chunker.py` — Shebang/content sniffing for extensionless scripts (e.g. `#!/usr/bin/env python`). Currently only extension and filename matching is used. Extensionless executable scripts in a project would be silently skipped.



- [ ] **L1** `cli.py:851-904` — No deduplication when a result appears in both code and docs search output.

- [ ] **L2** `cli.py` — No `--dry-run` mode for `prepare` to preview what would be indexed without building the database.

- [ ] **L3** `cli.py:936`, `database.py:376,417` — Snippets truncated without a `...` indicator; users don't know they're seeing partial content.

- [ ] **L4** `cli.py` — No single-file re-index; one changed file requires re-processing the entire directory.

- [ ] **L5** `github_distribution.py:253` — Checksum validation is skipped when the manifest download fails silently, allowing a corrupted database to be used.

- [ ] **L6** `cli.py:917,951,985` — Error messages reference `qrag mcp active` but the correct command is `qrag ai active`.

- [ ] **L7** `database.py` — No debug-level logging emitted under `--verbose` for database operations; makes slow or failing `prepare` runs hard to diagnose.
