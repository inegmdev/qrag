# qrag — Development Guide

This document covers setting up a local development environment, understanding the codebase, and contributing to qrag.

---

## Prerequisites

- Python 3.10+
- Git
- **uv** (recommended) — https://docs.astral.sh/uv/getting-started/installation/
  or pip (fallback)

---

## Clone & Setup

```bash
git clone https://github.com/inegmdev/qrag.git
cd qrag
```

**With uv (recommended):**

```bash
uv sync --extra dev
```

`uv sync` creates a `.venv` and installs all dependencies including dev extras automatically — no manual venv step needed.

**With pip (fallback):**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

---

## Project Structure

```
qrag/
├── src/qrag/
│   ├── __init__.py
│   ├── cli.py                  # Click CLI commands
│   ├── mcp_server.py           # JSON-RPC MCP server
│   ├── embedder.py             # Sentence-Transformers wrapper
│   ├── database.py             # SQLite + vector search operations
│   ├── chunker.py              # Tree-sitter C/C++ code parsing + chunking
│   ├── doc_parser.py           # PDF/HTML parsing + chunking
│   ├── config.py               # Config file management
│   └── github_distribution.py  # GitHub Releases integration
├── tests/
│   ├── fixtures/               # Sample C code, PDFs, HTML
│   └── test_*.py               # Unit tests
├── pyproject.toml
├── README.md
└── DEVELOPMENT.md
```

---

## Key Modules

**`embedder.py`** — Generates embeddings using `all-MiniLM-L6-v2` (384-dim, local, free).

**`chunker.py`** — Extracts code symbols with Tree-sitter; large functions auto-split into overlapping sub-chunks.

**`doc_parser.py`** — Parses PDFs (PyMuPDF) and HTML (BeautifulSoup) with heading hierarchy and feature tagging.

**`database.py`** — SQLite + sqlite-vec for vector search; exposes `search_code()`, `search_docs()`, `get_symbol()`, `list_symbols()`.

**`mcp_server.py`** — JSON-RPC 2.0 MCP server over stdio; implements the four MCP tools consumed by AI agents.

**`cli.py`** — Click command group: `prepare`, `ai`, `hub`, `status`, `info`, `search`, and more.

---

## Development Workflow

### Running Tests

```bash
uv run pytest
uv run pytest --cov=src/qrag tests/

# or with pip venv activated:
pytest
```

### Testing the CLI

```bash
uv run qrag --help
uv run qrag prepare -i tests/fixtures -o dev
uv run qrag search code "error correction"
uv run qrag search docs "configuration"
uv run qrag ai setup
```

### Testing the MCP Server

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | \
  uv run python -m qrag.mcp_server
```

---

## Building & Distributing

The embedding model (`all-MiniLM-L6-v2`) is bundled inside the wheel so users never need
a HuggingFace connection at runtime. The model files are gitignored and must be downloaded
into `src/qrag/models/` before building:

```bash
uv run python scripts/download_model.py   # downloads ~90 MB once
uv build
# or: pip install build && python -m build
```

Distribute a database via GitHub Releases:

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases

PYTHONPATH=src qrag prepare -i /path/to/source -i /path/to/docs -o v1.0
PYTHONPATH=src qrag hub push v1.0
```

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Add tests for new functionality
4. Ensure all tests pass: `pytest`
5. Submit a pull request
