# QuickRAG-TI

Semantic + structural code & documentation indexing for TI SDKs and technical docs, enabling LLM agents (Gemini, Claude) to quickly understand large vendor SDKs.

**Key Innovation:** One team member prepares the index once; the entire team uses pre-computed embeddings + symbol tables, dramatically reducing token usage and improving code understanding quality.

---

## Getting Started (Using QuickRAG-TI)

### Installation

Install the package:

```bash
pip install quickrag-ti
```

Or install from source:

```bash
git clone https://github.com/your-org/quickrag-ti.git
cd quickrag-ti
pip install -e .
```

### Quick Start

#### 1. Download a Pre-Built Database

Download an indexing database for your SoC (e.g., AM62x):

```bash
# List available databases
quickrag-ti list-databases

# Download a version
quickrag-ti download v1.0-am62x
```

#### 2. Set as Active Version

```bash
quickrag-ti mcp active v1.0-am62x
```

#### 3. Install MCP Server for Your AI Tool

**System-wide installation (recommended)** — Auto-detects and installs for all available agents:

```bash
quickrag-ti mcp install --global
```

This automatically detects which CLI agents (Gemini, Claude) are installed and registers the MCP server globally for all of them.

**Project-local installation** — If you prefer per-project configuration:

```bash
# For Gemini CLI only
quickrag-ti mcp install --ai=gemini

# For Claude (Claude Code) only
quickrag-ti mcp install --ai=claude
```

#### 4. Use in Your AI Agent

Once installed, your Gemini or Claude CLI will have access to four MCP tools:

- **`search_code(query)`** — Semantic search across SDK code (up to 10 results)
- **`search_trm(query)`** — Semantic search across TRM/documentation sections (up to 10 results)
- **`get_symbol_definition(symbol)`** — Get the exact definition of a function, struct, or macro
- **`list_symbols(pattern="")`** — List all symbols, optionally filtered by pattern

**Example:** Ask your agent:

> "How is ECC enabled in SRAM on AM62x? Show me the code and TRM section."

The agent will call the MCP tools, retrieve code + docs, and synthesize an answer using both.

#### 5. Check Status

```bash
# View active version and database paths
quickrag-ti mcp status

# View active version metadata (SoC, SDK version, embedding model)
quickrag-ti mcp info
```

### Advanced: Prepare Your Own Database

If you have a new SDK or documentation update, prepare a new indexing database:

```bash
quickrag-ti prepare \
  --soc AM62x \
  --sdk /path/to/ti-rtos-sdk \
  --docs /path/to/docs \
  --output v1.1-am62x
```

![quickrag-ti-prepare](docs/images/quickrag-ti-prepare.png)

This will:

1. Parse C/C++ source files using Tree-sitter
2. Extract functions, structs, and macros
3. Parse PDF/HTML documentation sections
4. Generate embeddings using Sentence-Transformers
5. Store results in SQLite databases (code.db + docs.db)
6. Automatically set as active version

Push to GitHub for team distribution:

```bash
quickrag-ti push v1.1-am62x
```

---

## Getting Started (Developing)

### Prerequisites

- Python 3.10+
- Git
- pip (or uv)

### Clone & Setup

```bash
git clone https://github.com/your-org/quickrag-ti.git
cd quickrag-ti

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

### Project Structure

```
quickrag-ti/
├── src/quickrag_ti/
│   ├── __init__.py
│   ├── cli.py              # Click CLI commands
│   ├── mcp_server.py       # JSON-RPC MCP server
│   ├── embedder.py         # Sentence-Transformers wrapper
│   ├── database.py         # SQLite + vector search operations
│   ├── chunker.py          # Tree-sitter C code parsing + chunking
│   ├── doc_parser.py       # PDF/HTML parsing + chunking
│   ├── config.py           # Config file management
│   ├── github_distribution.py  # GitHub Releases integration
│   └── utils.py
├── tests/
│   ├── fixtures/           # Sample C code, PDFs, HTML
│   └── test_*.py           # Unit tests
├── pyproject.toml
├── README.md
└── docs/
    ├── PRD.md              # Product requirements & design
    ├── progress.txt        # Implementation progress log
    └── issues/             # Issue tracking & specs
```

### Key Modules

**`embedder.py`** — Generates embeddings using `all-MiniLM-L6-v2` (384-dim, local, free)

- `embed(texts)` — Batch embed a list of strings
- `embed_one(text)` — Embed a single string

**`chunker.py`** — Extracts code symbols using Tree-sitter

- `chunk_c_file(path)` — Parse C/H file, return list of `CodeChunk` objects
- Large functions (>512 tokens) auto-split into overlapping sub-chunks

**`doc_parser.py`** — Parses PDFs (PyMuPDF) and HTML (BeautifulSoup)

- `parse_pdf(path, doc_type)` — Extract sections with heading hierarchy
- `parse_html(path, doc_type)` — Extract sections from HTML
- Font-size heuristics for heading detection; auto-tags feature names

**`database.py`** — SQLite + sqlite-vec for vector search

- `init_code_db()` / `init_docs_db()` — Create schema with vector tables
- `search_code()` / `search_docs()` — Semantic search by embedding distance
- `get_symbol()` — Exact lookup by symbol name
- `list_symbols()` — List all symbols with pattern filtering

**`mcp_server.py`** — JSON-RPC 2.0 MCP server over stdio

- Implements 4 MCP tools (search_code, search_trm, get_symbol_definition, list_symbols)
- Reads from active version's databases
- Entry points:
  - `quickrag-ti-mcp-server` — Installed command (preferred)
  - `python -m quickrag_ti.mcp_server` — Direct module invocation

**`cli.py`** — Click command group

- `prepare` — Index an SDK and/or docs
- `search-code` / `search-trm` — Debug search (for CLI testing)
- `get-symbol` — Look up a symbol by exact name
- `mcp active|status|info|install` — Manage active version and MCP registration
  - `mcp install --global` — Register MCP server system-wide for Gemini & Claude
  - `mcp install --ai=gemini|claude` — Register MCP server for a specific AI tool (project-local)
  - `mcp active <version>` — Set the active indexed database version
  - `mcp status` — Show active version and database status
  - `mcp info` — Display active version metadata
- `push|download|list-databases|delete` — GitHub distribution

### Development Workflow

#### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/quickrag_ti tests/

# Run specific test
pytest tests/test_chunker.py -v
```

#### Testing the CLI

```bash
# Set PYTHONPATH to use local source
PYTHONPATH=src quickrag-ti --help

# Test prepare command
PYTHONPATH=src quickrag-ti prepare \
  --soc AM62x \
  --sdk tests/fixtures \
  --output v0.0-dev

# Test search
PYTHONPATH=src quickrag-ti search-code "error correction"

# Test MCP install (system-wide)
PYTHONPATH=src quickrag-ti mcp install --global

# Test MCP install (project-local)
PYTHONPATH=src quickrag-ti mcp install --ai=claude
```

#### Testing the MCP Server

The MCP server reads JSON-RPC requests from stdin and writes responses to stdout:

```bash
# Start the server
PYTHONPATH=src python -m quickrag_ti.mcp_server

# In another terminal, send a JSON-RPC request
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | \
  PYTHONPATH=src python -m quickrag_ti.mcp_server
```

#### Debugging

Enable verbose output:

```bash
export DEBUG=1
PYTHONPATH=src quickrag-ti prepare --soc AM62x --sdk tests/fixtures --output v0.0-dev
```

### Modifying the Code

- **Adding a new MCP tool:** Add to `TOOLS` dict in `mcp_server.py`, implement the function, update tool signature
- **Adding a new CLI command:** Add a `@cli.command()` function in `cli.py`
- **Changing the embedding model:** Update `EMBEDDING_DIM` in `embedder.py` and `embed()` function
- **Changing database schema:** Update `init_code_db()` / `init_docs_db()` in `database.py` and migration logic

### Issue Tracking

Issues are tracked in `issues/INDEX.md` with acceptance criteria in individual files (e.g., `issues/001-*.md`).

Progress is logged in `docs/progress.txt` with timestamped updates after each issue is completed.

### Building & Distributing

Build a source distribution:

```bash
pip install build
python -m build
```

Distribute via GitHub Releases:

```bash
# Set your repo URL
export QUICKRAG_GITHUB_URL=https://github.com/your-org/quickrag-ti-databases

# Prepare and push
PYTHONPATH=src quickrag-ti prepare --soc AM62x --sdk ... --output v1.0-am62x
PYTHONPATH=src quickrag-ti push v1.0-am62x
```

### Dependencies

See `pyproject.toml` for the full list. Key ones:

- **click** — CLI framework
- **sentence-transformers** — Embeddings
- **sqlite-vec** — Vector search in SQLite
- **tree-sitter** + **tree-sitter-c** — C code parsing
- **pymupdf** — PDF parsing
- **beautifulsoup4** — HTML parsing

---

## Troubleshooting

**Q: "No active version set"**
A: Run `quickrag-ti mcp active <version>` to set one. Download with `quickrag-ti download` first if needed.

**Q: "code.db not found"**
A: Run `quickrag-ti prepare` to create one, or download a pre-built version.

**Q: MCP tools not showing in Claude/Gemini**
A: Re-run `quickrag-ti mcp install --global` (for global) or `quickrag-ti mcp install --ai=claude` (for project-local), then restart the AI tool. Verify with `gemini mcp list` or `claude mcp list`.

**Q: MCP server shows "Disconnected"**
A: This usually means the MCP server executable can't be found or isn't running properly. Ensure `quickrag-ti-mcp-server` is installed (`pip install -e .` from the project root) and try reinstalling with `quickrag-ti mcp install --global`.

**Q: Search returns no results**
A: Check that code.db exists with `quickrag-ti mcp status`, and that your query is semantically related to the indexed symbols.

---

## Contributing

Contributions welcome! Please:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Add tests for new functionality
4. Ensure tests pass (`pytest`)
5. Submit a pull request

---

## License

[Your License Here]

---

## Contact

Questions or feedback? Open an issue or contact the team.
