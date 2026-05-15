from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .config import (
    active_version_dir,
    code_db_path,
    docs_db_path,
    load_global,
    repo_url,
    save_global,
    set_repo_url,
    CACHE_DIR,
)


@click.group()
@click.version_option(__version__)
def cli():
    """QuickRAG-TI: semantic + structural search for TI SDKs and docs."""


# ---------------------------------------------------------------------------
# MCP active / status
# ---------------------------------------------------------------------------

@cli.command("mcp")
@click.argument("subcommand", type=click.Choice(["active", "status", "info", "install"]))
@click.argument("version", required=False)
@click.option("--ai", type=click.Choice(["gemini", "claude"]), help="AI tool to install for (required for install)")
@click.option("--global", "global_install", is_flag=True, help="Install MCP server system-wide for all projects (both gemini and claude)")
def mcp(subcommand: str, version: str | None, ai: str | None, global_install: bool):
    """Manage the active MCP version."""
    cfg = load_global()
    if subcommand == "active":
        if version is None:
            click.echo(f"Active version: {cfg.get('active_version') or '(none)'}")
        else:
            target = CACHE_DIR / version
            if not target.exists():
                click.echo(f"Version '{version}' not found in {CACHE_DIR}. Download it first.", err=True)
                sys.exit(1)
            cfg["active_version"] = version
            save_global(cfg)
            click.echo(f"Active version set to: {version}")
    elif subcommand == "status":
        click.echo(f"Active version : {cfg.get('active_version') or '(none)'}")
        db = code_db_path()
        click.echo(f"code.db path   : {db or '(not set)'}")
        click.echo(f"code.db exists : {db.exists() if db else False}")
        docs_db = docs_db_path()
        click.echo(f"docs.db path   : {docs_db or '(not set)'}")
        click.echo(f"docs.db exists : {docs_db.exists() if docs_db else False}")
    elif subcommand == "info":
        av = cfg.get("active_version")
        if not av:
            click.echo("No active version set.")
            return
        version_cfg_path = CACHE_DIR / av / "config.json"
        if version_cfg_path.exists():
            with open(version_cfg_path) as f:
                click.echo(json.dumps(json.load(f), indent=2))
        else:
            click.echo(f"No config.json found for version '{av}'.")
    elif subcommand == "install":
        if global_install:
            _mcp_install_global()
        else:
            if not ai:
                click.echo("Error: --ai=gemini|claude is required for install (or use --global)", err=True)
                sys.exit(1)
            _mcp_install(ai)


def _mcp_install(ai: str):
    """Install MCP server config for Gemini or Claude."""
    import shutil
    import subprocess

    mcp_cmd = shutil.which("quickrag-ti-mcp-server")
    if not mcp_cmd:
        click.echo("Error: quickrag-ti-mcp-server not found in PATH", err=True)
        sys.exit(1)

    if ai == "gemini":
        try:
            result = subprocess.run(
                ["gemini", "mcp", "add", "quickrag-ti", mcp_cmd],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                click.echo(f"✓ Gemini MCP server 'quickrag-ti' registered")
                click.echo(f"  Run `gemini mcp list` to verify installation")
            else:
                click.echo(f"Error: Failed to register MCP server with Gemini", err=True)
                click.echo(f"  {result.stderr}", err=True)
                sys.exit(1)
        except FileNotFoundError:
            click.echo(f"Error: Gemini CLI not found in PATH", err=True)
            click.echo(f"  Make sure Gemini CLI is installed and in your PATH", err=True)
            sys.exit(1)

    elif ai == "claude":
        try:
            result = subprocess.run(
                ["claude", "mcp", "add", "quickrag-ti", mcp_cmd],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                click.echo(f"✓ Claude MCP server 'quickrag-ti' registered")
                click.echo(f"  Run `claude mcp list` to verify installation")
            else:
                click.echo(f"Error: Failed to register MCP server with Claude", err=True)
                click.echo(f"  {result.stderr}", err=True)
                sys.exit(1)
        except FileNotFoundError:
            click.echo(f"Error: Claude CLI not found in PATH", err=True)
            click.echo(f"  Make sure Claude Code is installed and in your PATH", err=True)
            sys.exit(1)


def _detect_available_agents() -> list[str]:
    """Detect which CLI agents (gemini, claude) are available."""
    import shutil

    available = []
    if shutil.which("gemini"):
        available.append("gemini")
    if shutil.which("claude"):
        available.append("claude")
    return available


def _mcp_install_global_config(mcp_cmd: str, agent: str) -> bool:
    """Install MCP server to global config for a specific agent."""
    if agent == "gemini":
        config_file = Path.home() / ".gemini" / "settings.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        config = {}
        if config_file.exists():
            with open(config_file) as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError:
                    config = {}

        if "mcpServers" not in config:
            config["mcpServers"] = {}

        config["mcpServers"]["quickrag-ti"] = {
            "command": mcp_cmd,
            "args": [],
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        click.echo(f"✓ Gemini MCP server 'quickrag-ti' installed")
        click.echo(f"  Config: {config_file}")
        return True

    elif agent == "claude":
        config_file = Path.home() / ".claude.json"

        config = {}
        if config_file.exists():
            with open(config_file) as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError:
                    config = {}

        if "mcpServers" not in config:
            config["mcpServers"] = {}

        config["mcpServers"]["quickrag-ti"] = {
            "command": mcp_cmd,
            "args": [],
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        click.echo(f"✓ Claude MCP server 'quickrag-ti' installed")
        click.echo(f"  Config: {config_file}")
        return True

    return False


def _mcp_install_global():
    """Install MCP server system-wide for all available agents."""
    import shutil

    mcp_cmd = shutil.which("quickrag-ti-mcp-server")
    if not mcp_cmd:
        click.echo("Error: quickrag-ti-mcp-server not found in PATH", err=True)
        sys.exit(1)

    # Detect available agents
    available_agents = _detect_available_agents()
    if not available_agents:
        click.echo("Error: No CLI agents found (gemini or claude)", err=True)
        click.echo("Please install Gemini CLI or Claude Code first.", err=True)
        sys.exit(1)

    click.echo(f"Detected available agents: {', '.join(available_agents)}")
    click.echo()

    # Install for all available agents
    installed = []
    for agent in available_agents:
        if _mcp_install_global_config(mcp_cmd, agent):
            installed.append(agent)

    click.echo()
    if installed:
        agents_str = " and ".join(installed)
        click.echo(f"✓ MCP server is now available system-wide for {agents_str}!")
    else:
        click.echo("Warning: MCP server could not be installed to any agent.", err=True)


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--soc", required=True, help="SoC name, e.g. AM62x")
@click.option("--sdk", "sdk_path", type=click.Path(exists=True, path_type=Path), help="Path to SDK / C source root")
@click.option("--docs", "docs_path", type=click.Path(exists=True, path_type=Path), help="Path to docs root (PDF/HTML)")
@click.option("--output", required=True, help="Version label, e.g. v1.0-am62x")
def prepare(soc: str, sdk_path: Path | None, docs_path: Path | None, output: str):
    """Parse, embed, and store SDK sources and/or docs into a versioned database."""
    out_dir = CACHE_DIR / output
    out_dir.mkdir(parents=True, exist_ok=True)

    if sdk_path is None and docs_path is None:
        click.echo("Provide at least one of --sdk or --docs.", err=True)
        sys.exit(1)

    # ── Code indexing ──────────────────────────────────────────────────────
    if sdk_path is not None:
        from .chunker import chunk_c_file
        from .database import delete_chunks_for_file, init_code_db, insert_code_chunk
        from .embedder import embed

        db_path = out_dir / "code.db"
        init_code_db(db_path)

        c_files = sorted(sdk_path.rglob("*.c")) + sorted(sdk_path.rglob("*.h"))
        if not c_files:
            click.echo(f"No .c/.h files found under {sdk_path}", err=True)
            sys.exit(1)

        click.echo(f"[SDK] Found {len(c_files)} source file(s).")
        all_chunks = []
        with click.progressbar(c_files, label="  Chunking", width=60) as bar:
            for cf in bar:
                delete_chunks_for_file(db_path, str(cf))
                all_chunks.extend(chunk_c_file(cf))

        if not all_chunks:
            click.echo("No symbols extracted.", err=True)
            sys.exit(1)

        click.echo(f"  Extracted {len(all_chunks)} chunk(s). Embedding...")
        batch_size = 256
        code_stored = 0
        with click.progressbar(range(0, len(all_chunks), batch_size), label="  Embedding", width=60) as bar:
            for start in bar:
                batch = all_chunks[start : start + batch_size]
                embeddings = embed([c.code_text for c in batch])
                for chunk, emb in zip(batch, embeddings):
                    insert_code_chunk(
                        db_path,
                        symbol_name=chunk.symbol_name,
                        file_path=chunk.file_path,
                        line_start=chunk.line_start,
                        line_end=chunk.line_end,
                        code_text=chunk.code_text,
                        chunk_type=chunk.chunk_type,
                        embedding=emb,
                    )
                code_stored += len(batch)
        click.echo(f"  {code_stored} code chunks → {db_path}")

    # ── Docs indexing ──────────────────────────────────────────────────────
    if docs_path is not None:
        from .doc_parser import parse_pdf, parse_html
        from .database import delete_sections_for_source, init_docs_db, insert_doc_section
        from .embedder import embed

        ddb_path = out_dir / "docs.db"
        init_docs_db(ddb_path)

        doc_files = (
            sorted(docs_path.rglob("*.pdf"))
            + sorted(docs_path.rglob("*.html"))
            + sorted(docs_path.rglob("*.htm"))
        )
        if not doc_files:
            click.echo(f"No .pdf/.html files found under {docs_path}", err=True)
            sys.exit(1)

        click.echo(f"[Docs] Found {len(doc_files)} document(s).")
        all_sections = []
        with click.progressbar(doc_files, label="  Parsing", width=60) as bar:
            for df in bar:
                delete_sections_for_source(ddb_path, str(df))
                if df.suffix.lower() == ".pdf":
                    all_sections.extend(parse_pdf(df, doc_type="TRM"))
                else:
                    all_sections.extend(parse_html(df, doc_type="HTML"))

        if not all_sections:
            click.echo("No doc sections extracted.", err=True)
            sys.exit(1)

        click.echo(f"  Extracted {len(all_sections)} section(s). Embedding...")
        batch_size = 256
        docs_stored = 0
        with click.progressbar(range(0, len(all_sections), batch_size), label="  Embedding", width=60) as bar:
            for start in bar:
                batch = all_sections[start : start + batch_size]
                embeddings = embed([s.content for s in batch])
                for sec, emb in zip(batch, embeddings):
                    insert_doc_section(
                        ddb_path,
                        source_path=sec.source_path,
                        soc_name=soc,
                        doc_type=sec.doc_type,
                        chapter=sec.chapter,
                        section=sec.section,
                        subsection=sec.subsection,
                        title=sec.title,
                        content=sec.content,
                        page_range=sec.page_range,
                        feature_tags=sec.feature_tags,
                        embedding=emb,
                    )
                docs_stored += len(batch)
        click.echo(f"  {docs_stored} doc sections → {ddb_path}")

    version_cfg = {"soc": soc, "embedding_model": "all-MiniLM-L6-v2"}
    with open(out_dir / "config.json", "w") as f:
        json.dump(version_cfg, f, indent=2)

    cfg = load_global()
    cfg["active_version"] = output
    save_global(cfg)
    click.echo(f"Active version set to '{output}'.")


# ---------------------------------------------------------------------------
# search-code
# ---------------------------------------------------------------------------

@cli.command("search-code")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results to return")
def search_code(query: str, top_k: int):
    """Semantic search over indexed code chunks."""
    from .database import search_code as db_search
    from .embedder import embed_one

    db = code_db_path()
    if db is None:
        click.echo("No active version set. Run `quickrag-ti mcp active <version>`.", err=True)
        sys.exit(1)
    if not db.exists():
        click.echo(f"code.db not found at {db}. Run `quickrag-ti prepare` first.", err=True)
        sys.exit(1)

    q_emb = embed_one(query)
    results = db_search(db, q_emb, top_k=top_k)

    if not results:
        click.echo("No results found.")
        return

    for i, r in enumerate(results, 1):
        click.echo(
            f"\n[{i}] {r['symbol_name']}  ({r['type']})  score={r['similarity_score']}\n"
            f"    {r['file_path']}:{r['line_start']}-{r['line_end']}\n"
            f"    {r['code_snippet'][:120].replace(chr(10), ' ')}"
        )


# ---------------------------------------------------------------------------
# search-trm
# ---------------------------------------------------------------------------

@cli.command("search-trm")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results to return")
def search_trm(query: str, top_k: int):
    """Semantic search over indexed TRM / doc sections."""
    from .database import search_docs as db_search
    from .embedder import embed_one

    db = docs_db_path()
    if db is None:
        click.echo("No active version set. Run `quickrag-ti mcp active <version>`.", err=True)
        sys.exit(1)
    if not db.exists():
        click.echo(f"docs.db not found at {db}. Run `quickrag-ti prepare --docs` first.", err=True)
        sys.exit(1)

    q_emb = embed_one(query)
    results = db_search(db, q_emb, top_k=top_k)

    if not results:
        click.echo("No results found.")
        return

    for i, r in enumerate(results, 1):
        tags = ", ".join(r["feature_tags"]) if r["feature_tags"] else ""
        page = f"  p.{r['page_range']}" if r["page_range"] else ""
        click.echo(
            f"\n[{i}] {r['title']}  score={r['similarity_score']}{page}\n"
            f"    Tags: {tags}\n"
            f"    {r['content'][:160].replace(chr(10), ' ')}"
        )


# ---------------------------------------------------------------------------
# get-symbol
# ---------------------------------------------------------------------------

@cli.command("get-symbol")
@click.argument("name")
def get_symbol(name: str):
    """Print the full source of a symbol by exact name."""
    from .database import get_symbol as db_get_symbol

    db = code_db_path()
    if db is None:
        click.echo("No active version set. Run `quickrag-ti mcp active <version>`.", err=True)
        sys.exit(1)
    if not db.exists():
        click.echo(f"code.db not found at {db}. Run `quickrag-ti prepare` first.", err=True)
        sys.exit(1)

    result = db_get_symbol(db, name)
    if result is None:
        click.echo(f"Symbol '{name}' not found.")
        sys.exit(1)

    click.echo(
        f"Symbol : {result['symbol_name']}  ({result['type']})\n"
        f"File   : {result['file_path']}:{result['line_start']}-{result['line_end']}\n"
        f"\n{result['code_text']}"
    )


# ---------------------------------------------------------------------------
# GitHub distribution
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("version")
@click.option("--repo", type=click.Choice(["github", "jforge"]), default="github", help="Repository type")
@click.option("--force", is_flag=True, help="Overwrite existing release")
def push(version: str, repo: str, force: bool):
    """Push version databases to a repository."""
    if repo == "jforge":
        click.echo("Error: JForge support not yet implemented. Please wait for access credentials.", err=True)
        sys.exit(1)

    url = repo_url()
    if not url:
        click.echo("Error: No repo URL configured. Set it with environment or config.", err=True)
        sys.exit(1)

    version_dir = CACHE_DIR / version
    if not version_dir.exists():
        click.echo(f"Version '{version}' not found in {CACHE_DIR}.", err=True)
        sys.exit(1)

    from .github_distribution import push_to_github
    push_to_github(url, version, version_dir, force=force)


@cli.command("list-databases")
@click.option("--repo", type=click.Choice(["github", "jforge"]), default="github", help="Repository type")
def list_databases(repo: str):
    """List available databases on a repository."""
    if repo == "jforge":
        click.echo("Error: JForge support not yet implemented. Please wait for access credentials.", err=True)
        sys.exit(1)

    url = repo_url()
    if not url:
        click.echo("Error: No repo URL configured. Set it with environment or config.", err=True)
        sys.exit(1)

    from .github_distribution import list_databases as gh_list
    gh_list(url)


@cli.command()
@click.argument("version")
def download(version: str):
    """Download a version database from a repository."""
    url = repo_url()
    if not url:
        click.echo("Error: No repo URL configured. Set it with environment or config.", err=True)
        sys.exit(1)

    from .github_distribution import download_database
    download_database(url, version, CACHE_DIR)

    # Set as active version after successful download
    cfg = load_global()
    cfg["active_version"] = version
    save_global(cfg)
    click.echo(f"Active version set to '{version}'.")


@cli.command()
@click.argument("version")
def delete(version: str):
    """Delete a local version database."""
    version_dir = CACHE_DIR / version
    from .github_distribution import delete_database
    delete_database(version_dir)
