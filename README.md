# raghub

Build semantic RAG databases from your code and docs — once per team, instant for every AI agent.

**Key Innovation:** One team member prepares the index once; the entire team uses pre-computed embeddings + symbol tables, dramatically reducing token usage and improving code understanding quality.

---

## Getting Started (Using raghub)

### Installation

```bash
pip install raghub
```

Or install from source:

```bash
git clone https://github.com/your-org/raghub.git
cd raghub
pip install -e .
```

### Quick Start

#### 1. Download a Pre-Built Database

```bash
# List available databases
raghub list-databases

# Download a version
raghub download my-project
```

#### 2. Set as Active Version

```bash
raghub mcp active my-project
```

#### 3. Install for Your AI Agent

**Auto-detect and install for all available agents (recommended):**

```bash
raghub install
```

**Install for a specific agent:**

```bash
raghub install --ai=gemini
raghub install --ai=claude
```

You can also use the short alias `rhub` for any command:

```bash
rhub install
rhub prepare -i /path/to/docs -o my-project
```

#### 4. Use in Your AI Agent

Once installed, your Gemini or Claude CLI will have access to four MCP tools:

- **`search_code(query)`** — Semantic search across indexed code (up to 10 results)
- **`search_docs(query)`** — Semantic search across documentation sections (up to 10 results)
- **`get_symbol_definition(symbol)`** — Get the exact definition of a function, struct, or macro
- **`list_symbols(pattern="")`** — List all symbols, optionally filtered by pattern

**Example:** Ask your agent:

> "How is ECC enabled in SRAM? Show me the code and relevant doc section."

The agent will call the MCP tools, retrieve code + docs, and synthesize an answer.

#### 5. Check Status

```bash
raghub mcp status
raghub mcp info
```

### Advanced: Prepare Your Own Database

```bash
# Index code only
raghub prepare -i /path/to/sdk -o my-project

# Index docs only
raghub prepare -i /path/to/docs -o my-project

# Index both (separate dirs)
raghub prepare -i /path/to/sdk -i /path/to/docs -o my-project
```

Each `-i` directory is scanned automatically: `.c`/`.h` files go into `code.db`, `.pdf`/`.html`/`.htm` files go into `docs.db`. A directory containing both types will feed both databases.

This will:

1. Parse C/C++ source files using Tree-sitter
2. Extract functions, structs, and macros
3. Parse PDF/HTML documentation sections
4. Generate embeddings using Sentence-Transformers
5. Store results in SQLite databases (`code.db` + `docs.db`)
6. Automatically set as active version

Push to GitHub for team distribution:

```bash
raghub push my-project
```

---

## Getting Started (Developing)

### Prerequisites

- Python 3.10+
- Git
- pip (or uv)

### Clone & Setup

```bash
git clone https://github.com/your-org/raghub.git
cd raghub

python3 -m venv venv
source venv/bin/activate

pip install -e ".[dev]"
```

### Project Structure

```
raghub/
├── src/raghub/
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
└── README.md
```

### Key Modules

**`embedder.py`** — Generates embeddings using `all-MiniLM-L6-v2` (384-dim, local, free)

**`chunker.py`** — Extracts code symbols using Tree-sitter; large functions auto-split into overlapping sub-chunks

**`doc_parser.py`** — Parses PDFs (PyMuPDF) and HTML (BeautifulSoup) with heading hierarchy and feature tagging

**`database.py`** — SQLite + sqlite-vec for vector search; `search_code()`, `search_docs()`, `get_symbol()`, `list_symbols()`

**`mcp_server.py`** — JSON-RPC 2.0 MCP server over stdio; implements the 4 MCP tools

**`cli.py`** — Click command group (`prepare`, `install`, `mcp`, `push`, `download`, `list-databases`, `delete`, `search-code`, `search-docs`, `get-symbol`, `skills`)

### Development Workflow

#### Running Tests

```bash
pytest
pytest --cov=src/raghub tests/
```

#### Testing the CLI

```bash
PYTHONPATH=src raghub --help

PYTHONPATH=src raghub prepare -i tests/fixtures -o dev

PYTHONPATH=src raghub search-code "error correction"
PYTHONPATH=src raghub search-docs "configuration"
PYTHONPATH=src raghub install
```

#### Testing the MCP Server

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | \
  PYTHONPATH=src python -m raghub.mcp_server
```

### Building & Distributing

```bash
pip install build
python -m build
```

Distribute via GitHub Releases:

```bash
export RAGHUB_GITHUB_URL=https://github.com/your-org/raghub-databases

PYTHONPATH=src raghub prepare -i /path/to/sdk -i /path/to/docs -o v1.0
PYTHONPATH=src raghub push v1.0
```

---

## Troubleshooting

**Q: "No active version set"**
A: Run `raghub mcp active <version>` to set one. Download with `raghub download` first if needed.

**Q: "code.db not found"**
A: Run `raghub prepare` to create one, or download a pre-built version.

**Q: MCP tools not showing in Claude/Gemini**
A: Re-run `raghub install`, then restart the AI tool. Verify with `gemini mcp list` or `claude mcp list`.

**Q: MCP server shows "Disconnected"**
A: Ensure `raghub-mcp-server` is installed (`pip install -e .`) and try `raghub install` again.

**Q: Search returns no results**
A: Check status with `raghub mcp status`, and ensure your query is semantically related to indexed content.

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Add tests for new functionality
4. Ensure tests pass (`pytest`)
5. Submit a pull request

---

## License

[Your License Here]
