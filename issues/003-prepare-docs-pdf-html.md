# 003 — `prepare --docs` with PDF/HTML parsing

**Type:** AFK  
**Status:** Open  
**Blocked by:** [001](001-scaffold-search-code-e2e.md)

---

## What to build

Extend `quickrag-ti prepare` with a `--docs <path>` flag that ingests TRM PDFs, datasheet PDFs, and HTML pages into `~/.quickrag-ti/<version>/docs.db`. Sections are chunked at the heading level, preserving chapter/section hierarchy and page references. The `search-trm` CLI command queries this database.

After this slice, an agent can retrieve the relevant TRM section for a hardware feature by natural-language query.

## Acceptance criteria

- [ ] `prepare --docs <path>` ingests `.pdf` and `.html` files found recursively under the given path
- [ ] PDF parser (PyMuPDF preferred over PyPDF2) extracts text with chapter, section, and page number metadata
- [ ] HTML parser strips navigation/boilerplate and chunks by `<h2>` / `<h3>` headings
- [ ] Each `doc_sections` row carries `soc_name`, `doc_type`, `chapter`, `section`, `title`, `page_range`, `feature_tags`
- [ ] `quickrag-ti search-trm "ECC SRAM configuration"` returns the correct TRM section with page reference
- [ ] Results include `similarity_score` and are ranked descending
- [ ] Sections exceeding 512 tokens are split with overlap; page range spans the full original section
- [ ] A small fixture PDF (can be a generated/synthetic doc) is committed under `tests/fixtures/` for CI use

## Updates

<!-- Append timestamped notes here as work progresses -->
