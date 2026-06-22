# qrag

Build semantic RAG databases from your code and docs — once per team, instant for every AI agent.

**Key Innovation:** One team member prepares the index once; the entire team uses pre-computed embeddings + symbol tables, dramatically reducing token usage and improving code understanding quality.

---

## Getting Started (Using qrag)

### Installation

**From GitHub (latest, no PyPI required):**

```bash
pip install git+https://github.com/inegmdev/qrag.git@main
```

If you get a `setuptools` error (e.g. in corporate/offline environments), add `--no-build-isolation`:

```bash
pip install --no-build-isolation git+https://github.com/inegmdev/qrag.git@main
```

**From PyPI (once published):**

```bash
pip install qrag
```

**From source (for development):**

```bash
git clone https://github.com/inegmdev/qrag.git
cd qrag
pip install -e .
```

### Quick Start

#### 1. Download a Pre-Built Database

```bash
# List available databases
qrag list-databases

# Download a version
qrag download my-project
```

#### 2. Set as Active Version

```bash
qrag mcp active my-project
```

#### 3. Install for Your AI Agent

**Auto-detect and install for all available agents (recommended):**

```bash
qrag install
```

**Install for a specific agent:**

```bash
qrag install --ai=gemini
qrag install --ai=claude
```

#### 4. Use in Your AI Agent

Once installed, your Gemini or Claude CLI will have access to four MCP tools:

- **`search_code(query)`** — Semantic search across indexed code (up to 10 results)
- **`search_docs(query)`** — Semantic search across documentation sections (up to 10 results)
- **`get_symbol_definition(symbol)`** — Get the exact definition of a function, struct, or macro
- **`list_symbols(pattern="")`** — List all symbols, optionally filtered by pattern

#### 5. Check Status

```bash
qrag mcp status
qrag mcp info
```

### Advanced: Prepare Your Own Database

```bash
# Index code only
qrag prepare -i /path/to/source -o my-project

# Index docs only
qrag prepare -i /path/to/docs -o my-project

# Index both (separate dirs, or combine in one)
qrag prepare -i /path/to/source -i /path/to/docs -o my-project
```

Each `-i` directory is scanned automatically: `.c`/`.h`/`.cpp` files go into `code.db`, `.pdf`/`.html`/`.htm` files go into `docs.db`. A directory containing both types will feed both databases.

This will:

1. Parse C/C++ source files using Tree-sitter
2. Extract functions, structs, and macros
3. Parse PDF/HTML documentation sections
4. Generate embeddings using Sentence-Transformers
5. Store results in SQLite databases (`code.db` + `docs.db`)
6. Automatically set as active version

Push to GitHub for team distribution:

```bash
qrag push my-project
```

---

## Getting Started (Developing)

### Prerequisites

- Python 3.10+
- Git
- pip (or uv)

### Clone & Setup

```bash
git clone https://github.com/inegmdev/qrag.git
cd qrag

python3 -m venv venv
source venv/bin/activate

pip install -e ".[dev]"
```

### Project Structure

```
qrag/
├── src/qrag/
│   ├── __init__.py
│   ├── cli.py              # Click CLI commands
│   ├── mcp_server.py       # JSON-RPC MCP server
│   ├── embedder.py         # Sentence-Transformers wrapper
│   ├── database.py         # SQLite + vector search operations
│   ├── chunker.py          # Tree-sitter C/C++ code parsing + chunking
│   ├── doc_parser.py       # PDF/HTML parsing + chunking
│   ├── config.py           # Config file management
│   └── github_distribution.py  # GitHub Releases integration
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
pytest --cov=src/qrag tests/
```

#### Testing the CLI

```bash
PYTHONPATH=src qrag --help

PYTHONPATH=src qrag prepare -i tests/fixtures -o dev

PYTHONPATH=src qrag search-code "error correction"
PYTHONPATH=src qrag search-docs "configuration"
PYTHONPATH=src qrag install
```

#### Testing the MCP Server

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | \
  PYTHONPATH=src python -m qrag.mcp_server
```

### Building & Distributing

```bash
pip install build
python -m build
```

Distribute via GitHub Releases:

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases

PYTHONPATH=src qrag prepare -i /path/to/source -i /path/to/docs -o v1.0
PYTHONPATH=src qrag push v1.0
```

---

## CLI Reference

```
qrag [--verbose] [--version] COMMAND [OPTIONS]
```

| Command | Description |
|---------|-------------|
| `prepare -i DIR -o NAME` | Parse, embed, and store code/docs into a named database |
| `hub list` | List available versions on the repository |
| `hub download VERSION` | Download a version from the repository |
| `hub push VERSION [--force]` | Push a version to the repository |
| `hub delete VERSION` | Delete a local version |
| `status` | Show active version and database file paths |
| `info` | Show active version metadata |
| `harness active [VERSION]` | Show or set the active version |
| `harness setup [--ai gemini\|claude] [--global] [--mcp-only]` | Install AI harness (MCP + skills) for agents |
| `search QUERY` | Search all (code + docs + symbol); auto-detects best match |
| `search code QUERY [--top-k N]` | Semantic search over indexed code only |
| `search docs QUERY [--top-k N]` | Semantic search over indexed docs only |
| `search symbol NAME` | Look up exact symbol definition by name |
| `skills install [--ai gemini\|claude] [--global]` | Install the `/qrag` workflow skill |

Global flags: `--verbose` emits structured JSON logs to stderr.

---

## Troubleshooting

**Q: "No active version set"**
A: Run `qrag mcp active <version>` to set one. Download with `qrag download` first if needed.

**Q: "code.db not found"**
A: Run `qrag prepare` to create one, or download a pre-built version.

**Q: MCP tools not showing in Claude/Gemini**
A: Re-run `qrag install`, then restart the AI tool. Verify with `gemini mcp list` or `claude mcp list`.

**Q: MCP server shows "Disconnected"**
A: Ensure `qrag-mcp-server` is installed (`pip install -e .`) and try `qrag install` again.

**Q: Search returns no results**
A: Check status with `qrag mcp status`, and ensure your query is semantically related to indexed content.

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
