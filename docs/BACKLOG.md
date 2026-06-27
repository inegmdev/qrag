# qrag — Known Issues & Backlog

This file is the authoritative backlog of known bugs, missing features, and optimization opportunities, derived from a full codebase audit. Items are ordered by criticality within each tier.

When starting a new session, review this file and prefer working on higher-severity items first unless the user directs otherwise. When an item is resolved, mark it with `[x]` and note the fix briefly.

---

## Critical — Broken or Data-Loss Risk

> **IS1–IS5 are user-declared top priorities**. Work on these before any other open item.

- [x] **IS1** `cli.py` — Rich TUI with three transient progress bars (Overall / Parse / Embed), adaptive rolling-average ETA, and a uv-style single-line summary on completion. Fixed in feat/is1-is2-rich-tui-report: `rich>=13.0` added to `[build]` extras; disabled when `--verbose`.

- [x] **IS2** `cli.py` — Post-build audit report. Fixed in feat/is1-is2-rich-tui-report: `build-report.txt` written to `~/.qrag/<version>/` on every build with SUMMARY, BY LANGUAGE, CODE FILES, DOC FILES, and SKIPPED FILES sections; per-file elapsed time measured in workers.

- [x] **IS3** `database.py`, `mcp_server.py`, `cli.py` — Only one active database at a time. Fixed in PR #16: `active_version` (str) → `active_versions` (list) with auto-migration; `qrag ai active [v1 v2 …]` replaces the list; all MCP tools fan-out across active DBs via ThreadPoolExecutor, merge by score, dedup. `config.py` gains `add_active_version()`, `code_db_paths()`, `docs_db_paths()`.

- [x] **IS4** `doc_parser.py`, `database.py` — Document chunks are missing critical metadata for LLM citation. Fixed in feat/is4-is5-rich-metadata: added `doc_name`, `doc_revision` (_REV_RE from filename), `doc_status` (keyword in filename), `word_count`, `fig_table_refs` to `DocSection` and `doc_sections` schema; `search_docs` now returns `source_path` + all new fields; `_open_docs()` auto-migrates existing DBs.

- [x] **IS5** `chunker.py`, `database.py` — Code chunks lack metadata the LLM needs for precise citation and navigation. Fixed in feat/is4-is5-rich-metadata: added `file_name`, `parent_name`, `call_depth`, `chunk_index` to `CodeChunk` and `code_chunks` schema; `visit()` now tracks depth+parent through AST; `_split_large_chunk` sets `chunk_index`; `search_code` returns all new fields; `_open_code()` auto-migrates existing DBs.

- [x] **C0** `chunker.py`, `pyproject.toml`, `database.py`, `cli.py` — Only C and C++ were supported. Fixed in PR #12: replaced individual `tree-sitter-c`/`tree-sitter-cpp` deps with `tree-sitter-language-pack` (305+ grammars); rewrote `chunker.py` with a `_EXT_REGISTRY`/`_FILENAME_REGISTRY`-driven rule engine; chunk_type is now language-agnostic (function/class/struct/interface/enum/macro/type_alias/module/constant); added `language` column to `code_chunks` and `symbols` with auto-migration; `_detect_input_type()` now derives extensions from the registry; build system files (CMakeLists.txt, Makefile, Cargo.toml, package.json, go.mod, pom.xml, conanfile.py, *.cmake, *.gradle, *.toml, etc.) are indexed as first-class code alongside source files.

- [x] **C1** `mcp_server.py:226-229` — All exceptions silently swallowed with `continue`. Fixed in PR #11: `JSONDecodeError` → `-32700` response + log; unhandled `Exception` → `-32603` response + full traceback logged to `~/.qrag/logs/mcp_errors.log`; `KeyboardInterrupt`/`SystemExit` → clean exit 0; fatal loop crash → log + exit 1.

- [x] **C2** `cli.py:543,547` — `db_path`/`ddb_path` can be `None` in code-only or docs-only `build` runs, causing a `TypeError` crash. Fixed: added `db_path and` / `ddb_path and` guards on all four checkpoint/drain flush calls in `_consume_and_embed`.

- [x] **C3** `database.py` (multiple functions) — DB connections opened without `try/finally`. Fixed: wrapped all 13 open/close call-sites in `try/finally db.close()` — covers `init_code_db`, `init_docs_db`, `delete_chunks_for_file`, `insert_code_chunk`, `get_symbol`, `list_symbols`, `load_manifest`, `upsert_manifest_row`, `delete_manifest_row`, `delete_sections_for_source`, `insert_doc_section`, `search_docs`, `search_code`.

---

## High — Likely User-Facing Failures

- [ ] **GH#35** `pyproject.toml` — Default install downloads ~2.53 GB of CUDA libraries on Linux (sentence-transformers→torch chain). Partial fix in PR #39: `[tool.uv.sources]` redirects torch to CPU-only wheel for uv users (~220 MB). Full fix tracked in GH#38 (onnxruntime). [GitHub](https://github.com/inegmdev/qrag/issues/35)

- [ ] **GH#38** `embedder.py`, `pyproject.toml` — Replace sentence-transformers+torch with onnxruntime to eliminate CUDA baggage for all package managers (pip/pipx/uv). Reduces install from ~2.53 GB to ~30 MB for everyone. [GitHub](https://github.com/inegmdev/qrag/issues/38)

- [ ] **H0** `chunker.py`, `database.py` — Build-source relationship metadata: currently build system files (CMakeLists.txt, Cargo.toml, etc.) are indexed as isolated chunks. Phase 2 should enrich `code_chunks` with relational metadata — e.g. which source files belong to which cmake target/cargo bin/gradle task — so that RAG queries like "what files are compiled into the `my_app` executable?" return structured answers. Work: (1) add a `build_target` TEXT column to `code_chunks`; (2) parse cmake `add_executable`/`add_library` arguments to extract the source file list and back-link those source chunks to the target name; (3) do the same for Cargo `[[bin]]`→`src`, Gradle `sourceSets`, Maven `<module>` etc.; (4) expose `build_target` in `search_code` results so the AI agent can filter by target. Depends on C0.

- [ ] **H1** `database.py:249,378` — `feature_tags` stored as comma-CSV but split naively. Tags containing commas cause silent misalignment in search results.

- [ ] **H2** `database.py:350-422` — No validation that query embedding dimension matches `EMBEDDING_DIM=384`. A misconfigured model silently returns garbage search results.

- [x] **GH#23** `chunker.py` / `doc_parser.py` — Build fails with `'bytes' object is not an instance of 'str'` across `.js`, `.h`, `.c`, `.mk` files during the producer phase. Fixed in `pyproject.toml`: pinned `tree-sitter-language-pack<1.0.0` — v1.x (kreuzberg-dev "alef") changed `Parser.parse()` to require `str` not `bytes`; v0.x returns standard `tree_sitter.Parser` that accepts `bytes`. [GitHub](https://github.com/inegmdev/qrag/issues/23)

- [ ] **H3** `cli.py:436-440` — Producer exceptions are caught and appended to an errors list, but `build` still exits with code `0` and reports success. A corrupted or incomplete database looks valid.

- [ ] **H4** `cli.py:525` — If a producer thread dies without emitting a sentinel, `queue.get()` busy-loops indefinitely. The `build` command hangs forever with no error.

- [ ] **H5** `chunker.py:50` — Sub-chunk names (`func#0`, `func#1`) can collide with real symbol names. `INSERT OR REPLACE` silently overwrites the correct symbol entry.

- [ ] **H6** `config.py:29-31` — Malformed `~/.qrag/config.json` raises an uncaught `JSONDecodeError`, breaking every qrag command until the file is manually deleted.

- [x] **GH#28** `cli.py:1247` — Incremental delta broken on interrupted build: `upsert_manifest_rows_batch` called only after full `_consume_and_embed` completes; any interruption loses all manifest progress → full re-process on next run. Fixed in fix/gh28-gh29-build-safety: boundary tracking (`_code_recv`/`_code_flushed`) writes manifest rows per-file immediately after each flush inside `_consume_and_embed`. [GitHub](https://github.com/inegmdev/qrag/issues/28)

- [x] **GH#29** `cli.py:1065-1066` — `--force` silently deletes `code.db`/`docs.db` with no warning or confirmation prompt; users lose hours of build with a single flag. Fixed in fix/gh28-gh29-build-safety: shows DB summary (size, file count, last-built), requires `[y/N]` confirmation; `--yes`/`-y` skips for CI; non-TTY without `--yes` exits with error. [GitHub](https://github.com/inegmdev/qrag/issues/29)

- [ ] **GH#27** `cli.py` — Proportional CPU split: both `ProcessPoolExecutor` pools receive the same `limit_cpu`; dual builds over-subscribe cores → degraded throughput. Fix: split budget by file count ratio. [GitHub](https://github.com/inegmdev/qrag/issues/27)

- [ ] **GH#30** `cli.py` — No pre-build visualization of existing DB (size, file count, last-built) or delta preview (N changed, M new); no confirm-before-proceed prompt. [GitHub](https://github.com/inegmdev/qrag/issues/30)

- [x] **GH#31** `cli.py` — No resume-last-build: interrupted builds lose session state (input paths, device, progress); next run starts from scratch with no prompt to resume. Fixed in `feat/gh31-gh32-build-resume`: writes `<out-dir>/.qrag-build-state.json` after delta computation; detects it on next run with file count + %, shows resume prompt; `--no-resume` skips; non-TTY auto-resumes; state cleared on success and `--force`. [GitHub](https://github.com/inegmdev/qrag/issues/31)

- [x] **GH#32** `cli.py:1077-1085` — "Roots differ" restriction blocks incremental addition of new `-i` directories; forces `--force` full wipe even though existing data is valid. Fixed in `feat/gh31-gh32-build-resume`: removed the fatal check for both code and docs manifests; dropped roots are warned and cleaned up incrementally; new roots are processed as new files via existing delta logic. [GitHub](https://github.com/inegmdev/qrag/issues/32)

- [x] **GH#13** — Optimize Dependencies: Consumer vs. Builder Roles with Role-Based Installation. Split `pyproject.toml` into `dependencies` (consumer: click, sqlite-vec only) and `[project.optional-dependencies]` build/build.gpu/full groups; add `_ensure_builder_deps()` lazy-check in `build` command that detects GPU and prints actionable install instructions per package manager. [GitHub](https://github.com/inegmdev/qrag/issues/13)

- [x] **GH#18** `cli.py:274-391,431-481` — Add Antigravity CLI support alongside Gemini and Claude. Fixed in feat/gh18-antigravity-support: detect `agy` binary; write MCP config to `~/.gemini/config/mcp_config.json` (global) or `.agents/mcp_config.json` (local) via new `_write_mcp_config()` helper; install skill to `~/.gemini/config/skills/qrag/SKILL.md` (global) or `.agents/skills/qrag/SKILL.md` (local). [GitHub](https://github.com/inegmdev/qrag/issues/18)

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

- [ ] **L2** `cli.py` — No `--dry-run` mode for `build` to preview what would be indexed without building the database.

- [ ] **L3** `cli.py:936`, `database.py:376,417` — Snippets truncated without a `...` indicator; users don't know they're seeing partial content.

- [ ] **L4** `cli.py` — No single-file re-index; one changed file requires re-processing the entire directory.

- [ ] **L5** `github_distribution.py:253` — Checksum validation is skipped when the manifest download fails silently, allowing a corrupted database to be used.

- [ ] **L6** `cli.py:917,951,985` — Error messages reference `qrag mcp active` but the correct command is `qrag ai active`.

- [ ] **L7** `database.py` — No debug-level logging emitted under `--verbose` for database operations; makes slow or failing `build` runs hard to diagnose.

- [x] **GH#26** `cli.py`, `tui.py` — Rich TUI improvements:

---

## Feature — qrag explore (replaces hub)

> **GH#49 is the epic tracking issue.** Implement sub-issues in order #41 → #42 → #43 → #44 → #45 → #46 for vertical traceability. #47 and #48 are independent.

- [ ] **GH#49** [EPIC] — `qrag explore` replaces `qrag hub` entirely; unified TUI + multi-remote database explorer. Tracking issue for GH#41–48. [GitHub](https://github.com/inegmdev/qrag/issues/49)
- [ ] **GH#41** [EXPLORE-A] `cli.py`, `database.py` — MVP: `qrag explore list` (local Rich table) + `qrag explore stats <version>` (language %, symbol taxonomy, keyword tag cloud, staleness, coverage). Replaces `hub list`. [GitHub](https://github.com/inegmdev/qrag/issues/41)
- [ ] **GH#42** [EXPLORE-B] `cli.py`, `github_distribution.py` — GitHub remote integration: unified local+remote list, `explore download`, origin-remote stored in `~/.qrag/<v>/config.json`. Auth: `GITHUB_TOKEN` env → `gh` CLI. [GitHub](https://github.com/inegmdev/qrag/issues/42)
- [ ] **GH#43** [EXPLORE-C] `cli.py`, `config.py` — `qrag explore delete <version>`: confirmation prompt with size summary, `--yes` flag, auto-deactivates from `active_versions`. [GitHub](https://github.com/inegmdev/qrag/issues/43)
- [ ] **GH#44** [EXPLORE-D] `cli.py`, new backend modules — Additional remotes: HuggingFace Hub (`HF_TOKEN`/`huggingface-cli`), JFrog Artifactory (`JFROG_TOKEN`/`jf`), git+LFS. `explore add-remote`, `remove-remote`, `list-remotes`. [GitHub](https://github.com/inegmdev/qrag/issues/44)
- [ ] **GH#45** [EXPLORE-E] `cli.py` — `qrag explore push <version>`: pre-flight permission check, `--dry-run`, remote selection prompt for local DBs, `explore set-remote` command. [GitHub](https://github.com/inegmdev/qrag/issues/45)
- [ ] **GH#46** [EXPLORE-F] `tui.py` — `qrag explore` (no args): interactive Rich TUI browser — navigate DBs, view stats panel, delete/push/download/activate via key bindings. [GitHub](https://github.com/inegmdev/qrag/issues/46)
- [ ] **GH#47** [EXPLORE-G] `cli.py`, `database.py` — `qrag explore diff <v1> <v2>`: added/removed files + symbols, language % shift, new/removed keyword tags, `--json` output. [GitHub](https://github.com/inegmdev/qrag/issues/47)
- [ ] **GH#48** [EXPLORE-H] `cli.py` — `qrag explore push --all-remotes`: sequential multi-remote push, continue-on-failure, per-remote re-run hints. [GitHub](https://github.com/inegmdev/qrag/issues/48) proportional CPU split (GH#27), MVC extraction to `tui.py`, scrolling log panel, worker-count header, parse `files/s` rate, status line with live error/warning counts, smart path truncation, `fmt_eta` formatter, terminal-too-small fallback, spinners on hub/search commands. Fixed in `feat/gh26-tui-improvements`. [GitHub](https://github.com/inegmdev/qrag/issues/26)
