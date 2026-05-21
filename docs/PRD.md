# raghub: Complete System Design

**Project:** Semantic + Structural Code & Documentation Indexing for LLMs  
**Status:** Design Complete - Ready for Implementation  
**Date:** 2026-05-10

---

## 1. Executive Summary

**raghub** is a Python CLI tool and MCP server that enables teams to quickly understand large vendor SDKs (TI RTOS, Vector BSW) and technical documentation (TRMs, datasheets) by providing both semantic search (via embeddings) and structural navigation (via symbol indexing) to LLM agents (Gemini, Claude).

**Key Innovation:** One team member prepares the index once; the entire team uses pre-computed embeddings + symbol tables, dramatically reducing token usage and improving code understanding quality.

---

## 2. Problem Statement

- **Context Fragmentation:** Developers struggle to understand how features are implemented across 10k+ files in vendor SDKs
- **Navigation Overhead:** Manual grepping for symbols wastes time; keyword search returns noisy results
- **Knowledge Gaps:** TRMs and code are disconnected; developers can't correlate hardware capabilities with driver implementation
- **Team Inefficiency:** Every developer re-learns the same codebase without a shared semantic index

---

## 3. Solution Architecture

### 3.1 Technology Stack
- **Language:** Python 3.10+
- **Embeddings:** Sentence-Transformers (local, free, 384-dim vectors)
- **Vector DB:** SQLite with vector extension
- **Code Parsing:** Tree-sitter (C/C++)
- **Doc Parsing:** PyPDF2, openpyxl, html2text
- **MCP Protocol:** FastMCP (Python)
- **Distribution:** GitHub / JForge

### 3.2 High-Level Flow

```
PREPARATION (one person, runs once per SDK update):
  Source SDKs + Docs → Parse + Chunk → Embed → SQLite DBs → Push to GitHub

TEAM USAGE (all developers):
  Download v1.0-am62x → raghub mcp install --ai=gemini → Use in Gemini CLI

MCP RUNTIME:
  Agent query → MCP tools → SQLite search → Return results → Agent explains
```

---

## 4. Data Model

### 4.1 Database Schema

**code.db** (Code embeddings + symbol index):
```sql
CREATE TABLE code_chunks (
  id INTEGER PRIMARY KEY,
  symbol_name TEXT,
  file_path TEXT,
  line_start INTEGER,
  line_end INTEGER,
  code_text TEXT,
  embedding VECTOR(384),
  type TEXT -- "function", "struct", "macro", etc.
);

CREATE TABLE symbols (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE,
  type TEXT,
  file_path TEXT,
  line_number INTEGER,
  chunk_id INTEGER REFERENCES code_chunks(id)
);
```

**docs.db** (TRM/datasheet embeddings + metadata):
```sql
CREATE TABLE doc_sections (
  id INTEGER PRIMARY KEY,
  soc_name TEXT,
  doc_type TEXT, -- "TRM", "Datasheet", "AppNote"
  chapter INTEGER,
  section INTEGER,
  subsection TEXT,
  title TEXT,
  content TEXT,
  page_range TEXT,
  embedding VECTOR(384),
  feature_tags TEXT -- comma-separated
);
```

### 4.2 Config Files

**~/.raghub/config.json** (Global):
```json
{
  "repo_type": "github",
  "repo_url": "https://github.com/user/raghub-databases",
  "active_version": "v1.0-am62x",
  "cache_dir": "~/.raghub"
}
```

**~/.raghub/v1.0-am62x/config.json** (Version metadata):
```json
{
  "soc": "AM62x",
  "sdk_version": "09.00.01",
  "trm_version": "4.2",
  "created": "2026-05-10",
  "embedding_model": "all-MiniLM-L6-v2",
  "docs": ["TRM", "Datasheet"]
}
```

---

## 5. CLI Interface

### 5.1 Commands

**Discovery & Management:**
```bash
raghub list-databases [--repo github|jforge]
raghub download <version-soc>              # e.g., v1.0-am62x
raghub delete <version-soc>
```

**Database Preparation (one team member):**
```bash
raghub prepare \
  --soc AM62x \
  --sdk /path/to/ti-rtos \
  --docs /path/to/docs \
  --output v1.0-am62x

raghub push <version-soc> [--repo github|jforge]
```

**MCP Server Management:**
```bash
raghub mcp install --ai=gemini|claude
raghub mcp active <version-soc>
raghub mcp status
raghub mcp info
```

**Search (debugging):**
```bash
raghub search-code "query text"
raghub search-trm "query text"
```

---

## 6. MCP Tools

All tools operate on the active SoC (set via `raghub mcp active`):

### 6.1 search_code(query: str) → list[dict]
Semantic search across code embeddings. Returns function/struct definitions with snippets.

**Response:**
```json
[
  {
    "symbol_name": "enable_ecc",
    "file_path": "src/drivers/ecc.c",
    "line_start": 42,
    "line_end": 67,
    "code_snippet": "int enable_ecc() { ... }",
    "similarity_score": 0.94
  }
]
```

### 6.2 search_trm(query: str) → list[dict]
Semantic search across TRM/documentation sections.

**Response:**
```json
[
  {
    "chapter": 3,
    "section": 2,
    "title": "ECC Configuration",
    "content": "The ECC module is configured via...",
    "page_range": "pp. 42-47",
    "feature_tags": ["ECC", "SRAM", "Security"],
    "similarity_score": 0.91
  }
]
```

### 6.3 get_symbol_definition(symbol: str) → dict
Exact code definition for a symbol (function, struct, etc.).

**Response:**
```json
{
  "symbol_name": "enable_ecc",
  "type": "function",
  "file_path": "src/drivers/ecc.c",
  "line_start": 42,
  "line_end": 67,
  "code": "int enable_ecc() { ... }",
  "parameters": ["void"],
  "return_type": "int"
}
```

### 6.4 list_symbols(pattern: str = "") → list[dict]
List all symbols, optionally filtered by pattern.

**Response:**
```json
[
  {"name": "enable_ecc", "type": "function", "file": "...", "line": 42},
  {"name": "ECC_CONFIG", "type": "struct", "file": "...", "line": 15}
]
```

---

## 7. File Organization

### 7.1 Project Structure (GitHub/JForge repo)
```
raghub/
├── src/raghub/
│   ├── __init__.py
│   ├── cli.py                       # CLI commands
│   ├── embedder.py                  # Embedding & chunking
│   ├── database.py                  # SQLite operations
│   ├── mcp_server.py                # Generic MCP server
│   ├── doc_parser.py                # PDF/Excel/HTML parsing
│   ├── chunker.py                   # Code & doc chunking
│   └── utils.py
├── pyproject.toml
├── README.md
├── tests/
└── docs/
```

### 7.2 User Data Structure
```
~/.raghub/
├── config.json                       # Global config
├── v1.0-am62x/
│   ├── code.db                       # Code embeddings + symbols
│   ├── docs.db                       # TRM/datasheet embeddings
│   ├── config.json                   # Version metadata
│   └── manifest.json                 # SDK/doc versions
├── v1.0-j721e/
│   └── ...
└── mcp/
    └── mcp_server.py                 # Generated MCP server
```

---

## 8. Implementation Phases

### Phase 1: Core Infrastructure
- [ ] Project setup (pyproject.toml, package structure)
- [ ] SQLite schema + vector extension integration
- [ ] Sentence-Transformers embedding pipeline
- [ ] Tree-sitter C parser integration
- [ ] Document parser (PDF, Excel, HTML)

### Phase 2: CLI Tool
- [ ] Chunking logic (code functions, TRM sections)
- [ ] `prepare` command (parse, chunk, embed, store in SQLite)
- [ ] `push` / `download` commands (GitHub/JForge integration)
- [ ] `search-code` / `search-trm` commands (for testing)
- [ ] Database management (`list`, `delete`, `active`)

### Phase 3: MCP Server
- [ ] Generic MCP server (reads config, loads databases)
- [ ] MCP tool implementation (search_code, search_trm, get_symbol_definition, list_symbols)
- [ ] `mcp install --ai=gemini|claude` command
- [ ] Test with Gemini CLI

### Phase 4: Polish & Documentation
- [ ] Error handling, logging
- [ ] Tests (unit + integration)
- [ ] README, quickstart guide
- [ ] Example workflows

---

## 9. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **SoC-specific versioning** (v1.0-am62x) | Each SoC has unique driver + TRM; separate versions enable team collaboration |
| **Pre-computed embeddings** | One person pays embedding cost; team gets instant results |
| **SQLite + vector extension** | Single file per version, easy to distribute, no external DB dependency |
| **Sentence-Transformers** | Local, free, no API costs, good for code/technical docs |
| **Function-level chunking** | Tree-sitter already identifies boundaries; respects code structure |
| **Section-level TRM chunking** | Preserves document hierarchy; maintains page references |
| **Single active version** | Simplifies MCP tool signatures; context implicit in databases |

---

## 10. Success Criteria

- [ ] Team can download v1.0-am62x in <1 minute
- [ ] `raghub mcp install --ai=gemini` works without manual config
- [ ] Agent can answer "how is ECC enabled in SRAM on AM62x?" with code + TRM references
- [ ] Token usage for code understanding reduced by 40-60% vs. manual file reading
- [ ] Team consensus that code navigation is faster and more accurate

---

## 11. Open Questions / Future Work

1. **Vector BSW integration:** Deferred; can be added as separate versioned database
2. **Cross-SoC references:** If code reuses patterns across SoCs, consider linking
3. **Incremental updates:** Future: update individual files without full re-embedding
4. **Local embedding fine-tuning:** Could train on TI-specific code vocabulary
5. **Caching layer:** For repeated queries across team

---

**Design Complete. Ready for Implementation.**
