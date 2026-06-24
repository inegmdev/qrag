# qrag

Build semantic RAG databases from your code and docs — once per team, instant for every AI agent.

**Key idea:** One team member prepares the index once; the whole team uses pre-computed embeddings and symbol tables, dramatically reducing token usage and improving code-understanding quality.

---

## For End Users

> Your team has already built a database and shared it. Follow these steps to start using it with your AI agent.

### 1. Install qrag

**Recommended — installs into an isolated environment, no system-package conflicts:**

```bash
uv tool install git+https://github.com/inegmdev/qrag.git@main
```

> Don't have `uv`? Install it in seconds: https://docs.astral.sh/uv/getting-started/installation/

**From PyPI (once published):**

```bash
uv tool install qrag
```

**Fallback — if you prefer pip:**

```bash
pip install git+https://github.com/inegmdev/qrag.git@main
```

### 2. Point qrag at your team's database repository

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
```

Add this to your shell profile (`.bashrc`, `.zshrc`, etc.) so it persists across sessions.

### 3. Download the latest database

```bash
qrag hub list          # see what versions are available
qrag hub download v1.0 # download and set as active
```

### 4. Set up your AI agent

Auto-detect and install for all available agents (recommended):

```bash
qrag ai setup
```

Install for a specific agent:

```bash
qrag ai setup --ai=gemini
qrag ai setup --ai=claude
```

Verify the setup:

```bash
qrag status
```

Expected output:

```
Active version : v1.0
code.db path   : /home/user/.qrag/v1.0/code.db
code.db exists : True
docs.db path   : /home/user/.qrag/v1.0/docs.db
docs.db exists : True
```

### 5. Use in your AI agent

Restart your AI agent (Gemini CLI or Claude Code). You now have four tools available:

| Tool | Description |
|------|-------------|
| `search_code(query)` | Semantic search across indexed code (up to 10 results) |
| `search_docs(query)` | Semantic search across documentation sections (up to 10 results) |
| `get_symbol_definition(symbol)` | Get the exact definition of a function, struct, or macro |
| `list_symbols(pattern="")` | List all symbols, optionally filtered by a pattern |

Ask your agent natural questions about your codebase or documentation — it will call these tools automatically.

### Updating to a newer database version

When your team publishes a new version:

```bash
qrag hub list
qrag hub download v1.1
```

---

## For Database Preparers

> You are the team member responsible for indexing the codebase and docs and publishing the result.

### Prerequisites

- Python 3.10+
- GitHub CLI (`gh`) authenticated: `gh auth login`
- A GitHub repository to host the databases (e.g. `https://github.com/your-org/qrag-databases`)

### 1. Install qrag

```bash
uv tool install git+https://github.com/inegmdev/qrag.git@main
```

> Don't have `uv`? https://docs.astral.sh/uv/getting-started/installation/ — or use `pip install` as a fallback.

### 2. Configure the distribution repository

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
```

### 3. Build the index

Point `qrag` at directories containing code (`.c`/`.h`/`.cpp`) and/or docs (`.pdf`/`.html`). Content type is detected automatically.

```bash
qrag prepare \
  -i /path/to/source/ \
  -i /path/to/docs/ \
  -o v1.0
```

What happens under the hood:

1. `.c`/`.h`/`.cpp` files are parsed with Tree-sitter; functions, structs, and macros are extracted into `code.db`
2. `.pdf`/`.html` files are parsed section-by-section into `docs.db`
3. Embeddings are generated locally using Sentence-Transformers (`all-MiniLM-L6-v2`)
4. Both databases are stored at `~/.qrag/v1.0/` and the version is set as active

### 4. Verify locally before pushing

```bash
qrag search code "memory allocation"
qrag search docs "configuration guide"
```

### 5. Push to GitHub for team distribution

```bash
qrag hub push v1.0
```

### Updating the database

When source or docs change, build and push a new version:

```bash
qrag prepare -i /path/to/source/ -i /path/to/docs/ -o v1.1
qrag hub push v1.1
```

Notify your team to run `qrag hub download v1.1`.

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
| `ai active [VERSION]` | Show or set the active version |
| `ai setup [--ai gemini\|claude] [--global] [--mcp-only] [--skills-only]` | Install AI harness (MCP server + /qrag skill) |
| `search QUERY` | Search all (code + docs + symbols); auto-detects best match |
| `search code QUERY [--top-k N]` | Semantic search over indexed code only |
| `search docs QUERY [--top-k N]` | Semantic search over indexed docs only |
| `search symbol NAME` | Look up exact symbol definition by name |

Global flags: `--verbose` emits structured JSON logs to stderr.

---

## Troubleshooting

**Q: "No active version set"**
A: Run `qrag hub download <version>` to download one, then it will be set automatically.

**Q: "code.db not found"**
A: Run `qrag hub download <version>` to get a pre-built version, or ask your database preparer to publish one.

**Q: MCP tools not showing in Claude/Gemini**
A: Re-run `qrag ai setup`, then restart the AI tool.

**Q: MCP server shows "Disconnected"**
A: Ensure qrag is installed (`pip install ...`) and run `qrag ai setup` again.

**Q: Search returns no results**
A: Run `qrag status` to confirm databases are present; ensure your query is semantically related to indexed content.

**Q: "No GitHub authentication"**
A: Set the `GITHUB_TOKEN` environment variable or run `gh auth login`.

---

## For Developers

See [DEVELOPMENT.md](DEVELOPMENT.md) for how to set up a local development environment, run tests, and contribute to qrag.

---

## License

[Your License Here]
