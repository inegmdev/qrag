# 002 — `prepare --sdk` with tree-sitter C parsing

**Type:** AFK  
**Status:** Open  
**Blocked by:** [001](001-scaffold-search-code-e2e.md)

---

## What to build

Implement the `quickrag-ti prepare --soc <SOC> --sdk <path> --output <version>` command for C/C++ source trees. Tree-sitter extracts function and struct boundaries; the chunker splits oversized functions with a token-count fallback. Results land in `~/.quickrag-ti/<version>/code.db` with the symbols table populated for exact-lookup queries.

After this slice, `search-code` works on a real TI RTOS SDK tree, not just the toy fixture.

## Acceptance criteria

- [ ] `prepare --sdk` walks all `.c` / `.h` files under the given path
- [ ] Tree-sitter extracts functions, structs, and macros with correct `line_start` / `line_end`
- [ ] Functions exceeding 512 tokens are split into overlapping sub-chunks (overlap ≥ 64 tokens)
- [ ] All extracted symbols are inserted into the `symbols` table with `chunk_id` back-reference
- [ ] `quickrag-ti search-code "initialize DMA channel"` returns relevant results from the real SDK
- [ ] `quickrag-ti get-symbol <name>` (debug CLI alias for `get_symbol_definition`) prints the full function body
- [ ] Preparation of a 500-file SDK completes in under 10 minutes on a laptop (progress bar shown)
- [ ] Duplicate file paths on re-run are upserted, not duplicated

## Updates

<!-- Append timestamped notes here as work progresses -->
