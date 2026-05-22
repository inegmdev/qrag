# raghub

> This npm package is a name reservation stub. **raghub is a Python tool.**

## Install

```bash
pip install raghub
```

## Links

- **PyPI:** https://pypi.org/project/raghub
- **Source / docs:** https://github.com/islamegm/raghub

## What is raghub?

`raghub` builds semantic RAG databases from your code and documentation — once per team, instant for every AI agent. It indexes vendor SDKs (C/C++) and technical docs (TRMs, datasheets) with local embeddings, then serves them as an MCP server to LLM agents (Gemini CLI, Claude).

```bash
# Prepare once
raghub prepare --soc AM62x --sdk /path/to/ti-rtos --docs /path/to/docs --output v1.0-am62x

# Install MCP server for your AI agent
raghub mcp install --global

# Search from your AI agent
search_code("enable ECC on SRAM")
search_trm("ECC configuration registers")
```
