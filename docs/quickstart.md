# raghub Quickstart: AM62x SDK + TRM

This walkthrough covers the full flow for an AM62x project: one team member builds the database once; the whole team queries it instantly from Gemini or Claude.

---

## Prerequisites

- Python 3.10+
- `pip install raghub`
- GitHub CLI (`gh`) authenticated: `gh auth login`
- Gemini CLI or Claude Code installed

---

## Part A — Database Preparation (one team member, once per SDK update)

### 1. Gather your sources

```
/sdk/am62x/             # TI RTOS SDK — contains .c/.h driver files
/docs/am62x/            # AM62x TRM and datasheet — .pdf and .html files
```

### 2. Build the index

```bash
raghub prepare \
  -i /sdk/am62x/ \
  -i /docs/am62x/ \
  -o v1.0-am62x
```

raghub scans each `-i` directory automatically:
- `.c`/`.h` files → parsed with Tree-sitter → `code.db`
- `.pdf`/`.html` files → section-aware parser → `docs.db`

Typical output:

```
[code] /sdk/am62x/ — 4 827 .c/.h file(s)
[docs] /docs/am62x/ — 3 .pdf/.html file(s)
  Chunking code  [################]  4 827/4 827
  Extracted 38 412 chunk(s). Embedding...
  Embedding       [################]  38 412/38 412
  38 412 code chunks → ~/.raghub/v1.0-am62x/code.db
  Extracting docs [################]  3/3
  Extracted 214 section(s). Embedding...
  214 doc sections → ~/.raghub/v1.0-am62x/docs.db
Active version set to 'v1.0-am62x'.
```

### 3. Verify locally

```bash
raghub search-code "enable ECC on SRAM"
raghub search-docs "ECC configuration registers"
```

### 4. Push to GitHub for team distribution

```bash
export RAGHUB_GITHUB_URL=https://github.com/your-org/raghub-databases
raghub push v1.0-am62x
```

---

## Part B — Team Usage (every developer)

### 1. Configure the repo URL

```bash
export RAGHUB_GITHUB_URL=https://github.com/your-org/raghub-databases
# Or save it permanently:
raghub mcp active ""  # triggers config creation, then edit ~/.raghub/config.json
```

### 2. Download the database

```bash
raghub list-databases           # see what's available
raghub download v1.0-am62x     # downloads and sets as active version
```

### 3. Install the MCP server

```bash
raghub install                  # auto-detects gemini and/or claude
```

Verify:

```bash
raghub mcp status
```

Expected output:

```
Active version : v1.0-am62x
code.db path   : /home/user/.raghub/v1.0-am62x/code.db
code.db exists : True
docs.db path   : /home/user/.raghub/v1.0-am62x/docs.db
docs.db exists : True
```

### 4. Use in Gemini or Claude

Start your AI agent and ask:

> "How is ECC enabled on SRAM in the AM62x SDK? Show me the driver code and the relevant TRM section."

The agent will call `search_code` and `search_docs` in parallel, retrieve the top-ranked results, and synthesize a complete answer with file paths and page references.

---

## Updating the database

When the SDK or TRM is updated, the preparation team member runs:

```bash
raghub prepare -i /sdk/am62x/ -i /docs/am62x/ -o v1.1-am62x
raghub push v1.1-am62x
```

Team members switch to the new version:

```bash
raghub download v1.1-am62x
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No active version set` | Run `raghub mcp active v1.0-am62x` |
| `code.db not found` | Run `raghub download v1.0-am62x` |
| MCP tools not showing in Gemini/Claude | Re-run `raghub install`, restart the agent |
| `No GitHub authentication` | Set `GITHUB_TOKEN` or run `gh auth login` |
| Search returns no results | Check `raghub mcp status`; ensure query is semantically related to indexed content |
