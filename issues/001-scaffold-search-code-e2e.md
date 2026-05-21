# 001 — Project scaffold + `search-code` E2E on toy fixture

**Type:** AFK  
**Status:** Open  
**Blocked by:** None — can start immediately

---

## What to build

Bootstrap the Python package and wire up the full embed→store→query pipeline using a hardcoded toy C fixture (no tree-sitter yet). By the end of this slice, `raghub search-code "query"` must return ranked results from a small in-repo fixture file.

This slice establishes the real production schema (sqlite-vec BLOB storage, not a placeholder `VECTOR(384)` type), the embedding pipeline (Sentence-Transformers `all-MiniLM-L6-v2`), and the CLI entry point. Every later slice builds on top of this foundation.

## Acceptance criteria

- [ ] `pyproject.toml` defines the package with a `raghub` console script entry point
- [ ] `sqlite-vec` is the chosen vector extension; embeddings stored as BLOBs with correct byte layout
- [ ] A small fixture (`tests/fixtures/sample.c`, ~5–10 functions) is committed to the repo
- [ ] `raghub search-code "enable error correction"` returns at least one result with `symbol_name`, `file_path`, `line_start`, `line_end`, `similarity_score`
- [ ] Results are ranked by cosine similarity descending
- [ ] The DB used by `search-code` is the active version's `code.db` (path from config)
- [ ] `pyproject.toml` pins all direct dependencies with minimum versions

## Updates

<!-- Append timestamped notes here as work progresses -->
