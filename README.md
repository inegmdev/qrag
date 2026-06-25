# qrag

Build semantic RAG databases from your code and docs — once per team, instant for every AI agent.

**Key idea:** One team member prepares the index once; the whole team downloads pre-built SQLite databases and gets instant semantic + structural code/doc search inside their AI agent (Claude, Gemini CLI).

---

## For End Users (consumers)

> Your team has already built a database and shared it. Follow these steps to start using it.

### 1. Install qrag

```bash
uv tool install "git+https://github.com/inegmdev/qrag.git@main"
```

> Don't have `uv`? Install it: https://docs.astral.sh/uv/getting-started/installation/

**Upgrade to a newer version of qrag itself:**

```bash
uv tool install --reinstall "git+https://github.com/inegmdev/qrag.git@main"
```

### 2. Point qrag at your team's database repository

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
```

Add this to your shell profile (`.bashrc`, `.zshrc`, etc.) so it persists.

### 3. Download the database

```bash
qrag hub list             # see available versions
qrag hub download v1.0    # download and add to active set
```

You can download multiple databases and search across all of them simultaneously:

```bash
qrag hub download sdk-v1
qrag hub download rtos-v2
qrag hub download trm-v3
# All three are now active — searches fan out across all of them
```

### 4. Set up your AI agent

```bash
qrag ai setup             # auto-detect Claude and/or Gemini
qrag ai setup --ai=claude
qrag ai setup --ai=gemini
```

Verify the setup:

```bash
qrag status
```

Expected output (with multiple active databases):

```
Active versions: sdk-v1, rtos-v2
  [sdk-v1] code.db: /home/user/.qrag/sdk-v1/code.db (exists)
  [sdk-v1] docs.db: /home/user/.qrag/sdk-v1/docs.db (exists)
  [rtos-v2] code.db: /home/user/.qrag/rtos-v2/code.db (exists)
  [rtos-v2] docs.db: /home/user/.qrag/rtos-v2/docs.db (exists)
```

### 5. Use in your AI agent

Restart your AI agent (Claude Code or Gemini CLI). Four tools are now available:

| Tool | Description |
|------|-------------|
| `search_code(query)` | Semantic search across indexed code |
| `search_docs(query)` | Semantic search across documentation sections |
| `get_symbol_definition(symbol)` | Exact definition of a function, struct, macro, etc. |
| `list_symbols(pattern="")` | List all indexed symbols, optionally filtered |

Searches automatically fan out across all active databases, merge results by relevance score, and deduplicate before returning to the agent.

### Managing active databases

```bash
qrag ai active                        # show currently active versions
qrag ai active sdk-v1 rtos-v2        # replace the active list
```

### Updating to a newer database version

```bash
qrag hub list
qrag hub download v1.1    # auto-added to the active set
```

---

## For Database Preparers (builders)

> You are the team member responsible for indexing code/docs and publishing the result.

### Prerequisites

- Python 3.10+
- GitHub CLI (`gh`) authenticated: `gh auth login`
- A GitHub repository to host the databases (e.g. `https://github.com/your-org/qrag-databases`)

### 1. Install qrag with build dependencies

```bash
uv tool install "git+https://github.com/inegmdev/qrag.git@main[build]"
```

For GPU-accelerated embedding:

```bash
uv tool install "git+https://github.com/inegmdev/qrag.git@main[full]"
```

### 2. Configure the distribution repository

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
```

### 3. Build the index

Point `qrag` at directories containing source code and/or docs. Content type is detected automatically from file extensions and filenames.

```bash
qrag prepare \
  -i /path/to/source/ \
  -i /path/to/docs/ \
  -o v1.0
```

**Supported source types:**

- **Code:** C, C++, Rust, Python, Go, JavaScript, TypeScript, Java, C#, Ruby, Swift, Kotlin, Lua, Zig, and 30+ more languages via tree-sitter
- **Build files:** CMakeLists.txt, Makefile, Cargo.toml, package.json, go.mod, pom.xml, *.cmake, *.gradle, and more — indexed as first-class code
- **Docs:** PDF and HTML files, chunked section-by-section

What happens under the hood:

1. Source files are parsed with tree-sitter (305+ grammars); functions, structs, classes, macros, etc. are extracted into `code.db`
2. PDF/HTML files are parsed section-by-section into `docs.db`
3. Embeddings are generated locally using `all-MiniLM-L6-v2` (bundled, no network call)
4. Both databases are stored at `~/.qrag/v1.0/` and the version is added to the active set

### 4. Verify locally before pushing

```bash
qrag search code "memory allocation"
qrag search docs "configuration guide"
qrag search symbol "HAL_Init"
```

### 5. Push to GitHub for team distribution

```bash
qrag hub push v1.0
```

Notify your team to run `qrag hub download v1.0`.

### Updating the database

```bash
qrag prepare -i /path/to/source/ -i /path/to/docs/ -o v1.1
qrag hub push v1.1
```

---

## CLI Reference

```
qrag [--verbose] [--version] COMMAND [OPTIONS]
```

| Command | Description |
|---------|-------------|
| `prepare -i DIR -o NAME` | Parse, embed, and store code/docs into a named database |
| `status` | Show active versions and database file paths |
| `info` | Show active version metadata |
| `ai active [VERSION ...]` | Show or set active version(s); pass multiple to search across all |
| `ai setup [--ai claude\|gemini] [--global] [--mcp-only] [--skills-only]` | Install AI harness |
| `hub list` | List available versions on the configured repository |
| `hub download VERSION` | Download a version and add it to the active set |
| `hub push VERSION [--force]` | Push a version to the repository |
| `hub delete VERSION` | Delete a local version |
| `search QUERY` | Search code + docs + symbols; auto-detects best match |
| `search code QUERY [--top-k N]` | Semantic search over code |
| `search docs QUERY [--top-k N]` | Semantic search over docs |
| `search symbol NAME` | Exact symbol definition lookup |

Global flags: `--verbose` emits structured JSON logs to stderr.

---

## Troubleshooting

**Q: "No active version set"**  
A: Run `qrag hub download <version>` to download one — it is automatically added to the active set.

**Q: "code.db not found" / "docs.db not found"**  
A: Run `qrag hub download <version>` or ask your database preparer to publish one.

**Q: MCP tools not showing in Claude/Gemini**  
A: Re-run `qrag ai setup`, then restart the AI tool.

**Q: MCP server shows "Disconnected"**  
A: Ensure qrag is installed and on PATH, then re-run `qrag ai setup`.

**Q: Search returns no results**  
A: Run `qrag status` to confirm databases exist; check that `QRAG_GITHUB_URL` is set if using `hub` commands.

**Q: "No GitHub authentication"**  
A: Set the `GITHUB_TOKEN` environment variable or run `gh auth login`.

**Q: `prepare` fails with a missing-dependency error**  
A: You need the build extras. Reinstall with:
```bash
uv tool install --reinstall "git+https://github.com/inegmdev/qrag.git@main[build]"
```

---

## For Developers

See [DEVELOPMENT.md](DEVELOPMENT.md) for local setup, running tests, and contributing.

---

## License

[Your License Here]
