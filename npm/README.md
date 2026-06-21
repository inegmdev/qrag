# qrag

> This npm package is a name reservation stub. **qrag is a Python tool.**

## Install

```bash
pip install qrag
```

## Links

- **PyPI:** https://pypi.org/project/qrag
- **Source / docs:** https://github.com/inegmdev/qrag

## What is qrag?

`qrag` builds semantic RAG databases from your code and documentation — once per team, instant for every AI agent. It scans input directories, auto-detects code (C/C++) and docs (PDF/HTML), indexes them with local embeddings, and serves them as an MCP server to LLM agents (Gemini CLI, Claude).

```bash
# Index one or more directories — auto-detects code vs docs
qrag prepare -i /path/to/source -i /path/to/docs -o my-project

# Install MCP server for your AI agent
qrag install

# Search from your AI agent
search_code("memory allocation")
search_docs("configuration guide")
```
