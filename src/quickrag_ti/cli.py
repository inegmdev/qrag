from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .config import active_version_dir, code_db_path, load_global, save_global, CACHE_DIR


@click.group()
@click.version_option(__version__)
def cli():
    """QuickRAG-TI: semantic + structural search for TI SDKs and docs."""


# ---------------------------------------------------------------------------
# MCP active / status
# ---------------------------------------------------------------------------

@cli.command("mcp")
@click.argument("subcommand", type=click.Choice(["active", "status", "info"]))
@click.argument("version", required=False)
def mcp(subcommand: str, version: str | None):
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


# ---------------------------------------------------------------------------
# prepare (slice 001: regex C parsing, no tree-sitter)
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--soc", required=True, help="SoC name, e.g. AM62x")
@click.option("--sdk", "sdk_path", type=click.Path(exists=True, path_type=Path), help="Path to SDK / C source root")
@click.option("--output", required=True, help="Version label, e.g. v1.0-am62x")
def prepare(soc: str, sdk_path: Path | None, output: str):
    """Parse, embed, and store SDK sources into a versioned database."""
    from .chunker import chunk_c_file
    from .database import init_code_db, insert_code_chunk
    from .embedder import embed

    out_dir = CACHE_DIR / output
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "code.db"
    init_code_db(db_path)

    if sdk_path is None:
        click.echo("No --sdk path provided; nothing to index.", err=True)
        sys.exit(1)

    c_files = list(sdk_path.rglob("*.c")) + list(sdk_path.rglob("*.h"))
    if not c_files:
        click.echo(f"No .c/.h files found under {sdk_path}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(c_files)} source file(s). Chunking...")
    all_chunks = []
    for cf in c_files:
        all_chunks.extend(chunk_c_file(cf))

    if not all_chunks:
        click.echo("No functions extracted.", err=True)
        sys.exit(1)

    click.echo(f"Extracted {len(all_chunks)} chunk(s). Embedding (this may take a moment)...")
    texts = [c.code_text for c in all_chunks]
    embeddings = embed(texts)

    for chunk, emb in zip(all_chunks, embeddings):
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

    version_cfg = {"soc": soc, "embedding_model": "all-MiniLM-L6-v2"}
    with open(out_dir / "config.json", "w") as f:
        json.dump(version_cfg, f, indent=2)

    cfg = load_global()
    cfg["active_version"] = output
    save_global(cfg)

    click.echo(f"Done. {len(all_chunks)} chunks stored in {db_path}")
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
