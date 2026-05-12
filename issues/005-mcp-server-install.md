# 005 — MCP server + `mcp install`

**Type:** AFK  
**Status:** Open  
**Blocked by:** [002](002-prepare-sdk-tree-sitter.md), [003](003-prepare-docs-pdf-html.md)

---

## What to build

Implement the FastMCP server exposing four tools (`search_code`, `search_trm`, `get_symbol_definition`, `list_symbols`) and the `quickrag-ti mcp install --ai=gemini|claude` command that writes the AI tool's config file to register the server. The MCP server entry point is the installed package itself — no generated copy under `~/.quickrag-ti/mcp/`.

After this slice, a Gemini or Claude agent can answer questions like "how is ECC enabled in SRAM on AM62x?" by calling the MCP tools against the active version's databases.

## Acceptance criteria

- [ ] `quickrag-ti mcp install --ai=gemini` writes the correct Gemini CLI MCP config entry pointing to the installed `quickrag-ti` package entry point
- [ ] `quickrag-ti mcp install --ai=claude` writes the correct Claude MCP config entry
- [ ] `quickrag-ti mcp active <version>` sets `active_version` in `~/.quickrag-ti/config.json`
- [ ] `quickrag-ti mcp status` shows the active version, the path to both DBs, and whether the MCP server entry is registered in the detected AI tool config
- [ ] `quickrag-ti mcp info` prints the active version's `config.json` metadata (SoC, SDK version, TRM version, embedding model)
- [ ] `search_code(query)` returns up to 10 results ranked by cosine similarity
- [ ] `search_trm(query)` returns up to 10 results ranked by cosine similarity
- [ ] `get_symbol_definition(symbol)` returns exact match from the `symbols` table; returns a structured error if not found
- [ ] `list_symbols(pattern="")` returns all symbols, filtered by case-insensitive substring match when pattern is provided
- [ ] Gemini CLI successfully answers "how is ECC enabled in SRAM on AM62x?" using code + TRM results (manual smoke test documented in Updates)

## Updates

<!-- Append timestamped notes here as work progresses -->
