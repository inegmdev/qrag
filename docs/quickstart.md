# qrag Quickstart

This walkthrough covers the full flow: one team member builds the database once; the whole team queries it instantly from Gemini or Claude.

---

## Prerequisites

- Python 3.10+
- `pip install qrag`
- GitHub CLI (`gh`) authenticated: `gh auth login`
- Gemini CLI or Claude Code installed

---

## Part A — Database Preparation (one team member, once per update)

### 1. Gather your sources

Point `qrag` at any directories containing code (`.c`/`.h`/`.cpp`) and/or docs (`.pdf`/`.html`). Content type is detected automatically.

```
/path/to/source/        # C/C++ source files
/path/to/docs/          # PDF and HTML documentation
```

### 2. Build the index

```bash
qrag build \
  -i /path/to/source/ \
  -i /path/to/docs/ \
  -o v1.0
```

qrag scans each `-i` directory automatically:
- `.c`/`.h`/`.cpp` files → parsed with Tree-sitter → `code.db`
- `.pdf`/`.html` files → section-aware parser → `docs.db`

Typical output:

```
[code] /path/to/source/ — 4 827 .c/.h/.cpp file(s)
[docs] /path/to/docs/ — 3 .pdf/.html file(s)
  Chunking code  [################]  4 827/4 827
  Extracted 38 412 chunk(s). Embedding...
  Embedding       [################]  38 412/38 412
  38 412 code chunks → ~/.qrag/v1.0/code.db
  Extracting docs [################]  3/3
  Extracted 214 section(s). Embedding...
  214 doc sections → ~/.qrag/v1.0/docs.db
Active version set to 'v1.0'.
```

### 3. Verify locally

```bash
qrag search-code "memory allocation"
qrag search-docs "configuration guide"
```

### 4. Push to GitHub for team distribution

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
qrag push v1.0
```

---

## Part B — Team Usage (every developer)

### 1. Configure the repo URL

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
```

### 2. Download the database

```bash
qrag list-databases        # see what's available
qrag download v1.0         # downloads and sets as active version
```

### 3. Install the MCP server

```bash
qrag install               # auto-detects gemini and/or claude
```

Verify:

```bash
qrag mcp status
```

Expected output:

```
Active version : v1.0
code.db path   : /home/user/.qrag/v1.0/code.db
code.db exists : True
docs.db path   : /home/user/.qrag/v1.0/docs.db
docs.db exists : True
```

### 4. Use in Gemini or Claude

Start your AI agent and ask natural questions about your codebase or documentation. The agent will call `search_code` and `search_docs` in parallel, retrieve the top-ranked results, and synthesize a complete answer with file paths and page references.

---

## Updating the database

When source or docs are updated, run:

```bash
qrag build -i /path/to/source/ -i /path/to/docs/ -o v1.1
qrag push v1.1
```

Team members switch to the new version:

```bash
qrag download v1.1
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No active version set` | Run `qrag mcp active <version>` |
| `code.db not found` | Run `qrag download <version>` |
| MCP tools not showing in Gemini/Claude | Re-run `qrag install`, restart the agent |
| `No GitHub authentication` | Set `GITHUB_TOKEN` or run `gh auth login` |
| Search returns no results | Check `qrag mcp status`; ensure query is semantically related to indexed content |
