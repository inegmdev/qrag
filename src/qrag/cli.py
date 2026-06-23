from __future__ import annotations

import json
import logging as _logging
import os
import queue
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
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

_logger = _logging.getLogger("qrag")


class _JsonFormatter(_logging.Formatter):
    def format(self, record: _logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        })


QRAG_SKILL_CONTENT = """Search the local RAG database iteratively to answer a question about code or documentation.

## Workflow

Given: $ARGUMENTS (your question or topic)

1. **Think first**: Decompose the question — what concept am I looking for in docs? What symbol/function in code? Write your search intent before calling tools.

2. **Search in parallel**: Call `search_docs` and `search_code` (both MCP tools) simultaneously with targeted queries. If only docs or only code apply, search only what is relevant.

3. **Assess results**: For each result set, note the similarity scores and excerpt relevance. State explicitly what you found and what remains unanswered.

4. **Iterate if needed**: Refine your query and search again. Stop iterating when:
   - You have a high-confidence answer with supporting evidence, OR
   - Two consecutive rounds return no new information (low scores, repeated results), OR
   - The topic is clearly outside the indexed content.

5. **Check in with the user** every 2–3 rounds: briefly state what you have found so far and ask if you should continue or refocus.

6. **If information is not found**: Tell the user the topic is not in the local database. Suggest searching online and offer to help index new content with `qrag prepare -i <path>`.

7. **Conclude**: Synthesize all findings into a clear answer. Cite source file paths, symbol names, doc sections, and page numbers. Flag any inconsistencies between docs and code.

## Available MCP tools
- `search_code(query, top_k)` — semantic search over indexed code symbols
- `search_docs(query, top_k)` — semantic search over indexed documentation
- `list_symbols(pattern)` — list code symbols matching a glob pattern
- `get_symbol(name)` — retrieve full source of a specific symbol
"""


@click.group()
@click.version_option(__version__)
@click.option("--verbose", is_flag=True, help="Emit structured JSON logs to stderr")
@click.pass_context
def cli(ctx, verbose: bool):
    """qrag: build semantic RAG databases from your code and docs."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    if verbose:
        handler = _logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        _logger.addHandler(handler)
        _logger.setLevel(_logging.DEBUG)


# ---------------------------------------------------------------------------
# HARNESS — AI agent integration (MCP, skills, and other interfaces)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# STATUS — Check active version and configuration
# ---------------------------------------------------------------------------

@cli.command("status")
def status():
    """Show active version and database file paths."""
    cfg = load_global()
    click.echo(f"Active version : {cfg.get('active_version') or '(none)'}")
    db = code_db_path()
    click.echo(f"code.db path   : {db or '(not set)'}")
    click.echo(f"code.db exists : {db.exists() if db else False}")
    docs_db = docs_db_path()
    click.echo(f"docs.db path   : {docs_db or '(not set)'}")
    click.echo(f"docs.db exists : {docs_db.exists() if docs_db else False}")


@cli.command("info")
def info():
    """Show active version metadata."""
    cfg = load_global()
    av = cfg.get("active_version")
    if not av:
        click.echo("No active version set. Run 'qrag download <version>' first.")
        sys.exit(1)
    version_cfg_path = CACHE_DIR / av / "config.json"
    if version_cfg_path.exists():
        with open(version_cfg_path) as f:
            click.echo(json.dumps(json.load(f), indent=2))
    else:
        click.echo(f"No config.json found for version '{av}'.")


@cli.group("ai", invoke_without_command=False)
def ai():
    """Manage the AI harness (MCP server, skills, and future interfaces)."""
    pass


@ai.command("active")
@click.argument("version", required=False)
def ai_active(version: str | None):
    """Show or set the active version."""
    cfg = load_global()
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


@ai.command("setup")
@click.option("--ai", "agent", type=click.Choice(["gemini", "claude"]), help="AI tool to install for (required unless --global)")
@click.option("--global", "global_install", is_flag=True, help="Install AI harness system-wide for all projects (both gemini and claude)")
@click.option("--mcp-only", is_flag=True, help="Install MCP server only (skip /qrag skill)")
@click.option("--skills-only", is_flag=True, help="Install /qrag skill only (skip MCP server)")
def ai_setup(agent: str | None, global_install: bool, mcp_only: bool, skills_only: bool):
    """Install the AI harness (MCP server + /qrag skill).

    Use --mcp-only or --skills-only to install just one component of the AI harness.
    """
    if mcp_only and skills_only:
        click.echo("Error: --mcp-only and --skills-only are mutually exclusive.", err=True)
        sys.exit(1)

    if not global_install and not agent:
        click.echo("Error: --ai=gemini|claude is required (or use --global)", err=True)
        sys.exit(1)

    # Install MCP server (unless --skills-only)
    if not skills_only:
        if global_install:
            _mcp_install_global()
        else:
            _mcp_install(agent)

    # Install /qrag skill (unless --mcp-only)
    if not mcp_only:
        click.echo()
        if global_install:
            _skills_install_global()
        else:
            _skills_install(agent, global_install=False)


def _mcp_install(ai: str):
    """Install MCP server config for Gemini or Claude."""
    import shutil
    import subprocess

    mcp_cmd = shutil.which("qrag-mcp-server")
    if not mcp_cmd:
        click.echo("Error: qrag-mcp-server not found in PATH", err=True)
        sys.exit(1)

    if ai == "gemini":
        try:
            result = subprocess.run(
                ["gemini", "mcp", "add", "qrag", mcp_cmd],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                click.echo("✓ Gemini MCP server 'qrag' registered")
                click.echo("  Run `gemini mcp list` to verify installation")
            else:
                click.echo("Error: Failed to register MCP server with Gemini", err=True)
                click.echo(f"  {result.stderr}", err=True)
                sys.exit(1)
        except FileNotFoundError:
            click.echo("Error: Gemini CLI not found in PATH", err=True)
            click.echo("  Make sure Gemini CLI is installed and in your PATH", err=True)
            sys.exit(1)

    elif ai == "claude":
        try:
            result = subprocess.run(
                ["claude", "mcp", "add", "qrag", mcp_cmd],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                click.echo("✓ Claude MCP server 'qrag' registered")
                click.echo("  Run `claude mcp list` to verify installation")
            else:
                click.echo("Error: Failed to register MCP server with Claude", err=True)
                click.echo(f"  {result.stderr}", err=True)
                sys.exit(1)
        except FileNotFoundError:
            click.echo("Error: Claude CLI not found in PATH", err=True)
            click.echo("  Make sure Claude Code is installed and in your PATH", err=True)
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

        config["mcpServers"]["qrag"] = {
            "command": mcp_cmd,
            "args": [],
            "trust": True,
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        click.echo("✓ Gemini MCP server 'qrag' installed")
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

        config["mcpServers"]["qrag"] = {
            "command": mcp_cmd,
            "args": [],
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        click.echo("✓ Claude MCP server 'qrag' installed")
        click.echo(f"  Config: {config_file}")
        return True

    return False


def _mcp_install_global():
    """Install MCP server system-wide for all available agents."""
    import shutil

    mcp_cmd = shutil.which("qrag-mcp-server")
    if not mcp_cmd:
        click.echo("Error: qrag-mcp-server not found in PATH", err=True)
        sys.exit(1)

    available_agents = _detect_available_agents()
    if not available_agents:
        click.echo("Error: No CLI agents found (gemini or claude)", err=True)
        click.echo("Please install Gemini CLI or Claude Code first.", err=True)
        sys.exit(1)

    click.echo(f"Detected available agents: {', '.join(available_agents)}")
    click.echo()

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
# install (top-level shortcut: auto-installs MCP for all detected agents)
# ---------------------------------------------------------------------------



def _skills_install(ai: str, global_install: bool) -> None:
    """Install qrag.md skill for a specific agent."""
    if ai == "claude":
        if global_install:
            cmd_dir = Path.home() / ".claude" / "commands"
        else:
            cmd_dir = Path.cwd() / ".claude" / "commands"
    elif ai == "gemini":
        if global_install:
            cmd_dir = Path.home() / ".gemini" / "commands"
        else:
            cmd_dir = Path.cwd() / ".gemini" / "commands"
    else:
        click.echo(f"Error: Unknown AI tool '{ai}'", err=True)
        sys.exit(1)

    cmd_dir.mkdir(parents=True, exist_ok=True)
    skill_file = cmd_dir / "qrag.md"

    with open(skill_file, "w") as f:
        f.write(QRAG_SKILL_CONTENT)

    click.echo(f"✓ Installed /qrag skill for {ai}")
    click.echo(f"  File: {skill_file}")


def _skills_install_global() -> None:
    """Install qrag.md skill for all detected agents (global)."""
    available_agents = _detect_available_agents()
    if not available_agents:
        click.echo("Error: No CLI agents found (gemini or claude)", err=True)
        click.echo("Please install Gemini CLI or Claude Code first.", err=True)
        sys.exit(1)

    click.echo(f"Detected available agents: {', '.join(available_agents)}")
    click.echo()

    installed = []
    for agent in available_agents:
        try:
            _skills_install(agent, global_install=True)
            installed.append(agent)
        except Exception as e:
            click.echo(f"Warning: Failed to install skill for {agent}: {e}", err=True)

    click.echo()
    if installed:
        agents_str = " and ".join(installed)
        click.echo(f"✓ /qrag skill is now available system-wide for {agents_str}!")
    else:
        click.echo("Warning: /qrag skill could not be installed to any agent.", err=True)


# ---------------------------------------------------------------------------
# BUILD — Create and manage indexes
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _detect_input_type(d: Path) -> tuple[list[Path], list[Path]]:
    """Return (code_files, doc_files) found under d."""
    code = (
        sorted(d.rglob("*.c"))
        + sorted(d.rglob("*.h"))
        + sorted(d.rglob("*.cpp"))
    )
    docs = (
        sorted(d.rglob("*.pdf"))
        + sorted(d.rglob("*.html"))
        + sorted(d.rglob("*.htm"))
    )
    return code, docs


_QUEUE_MAXSIZE = 4096
_CHECKPOINT_SIZE = 1000
_KIND_CODE = "code"
_KIND_DOC = "doc"


def _run_code_producer(
    to_process: dict,
    workers: int | None,
    q: queue.Queue,
    errors: list,
) -> None:
    from .chunker import chunk_code_file
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(chunk_code_file, abs_p): (root, rel)
            for (root, rel), abs_p in to_process.items()
        }
        for future in as_completed(futures):
            root, rel = futures[future]
            try:
                chunks = future.result()
                q.put((_KIND_CODE, chunks, root, rel))
            except Exception as e:
                errors.append(f"chunk {Path(root) / rel}: {e}")
    q.put(None)  # sentinel


def _run_doc_producer(
    to_process_docs: dict,
    workers: int | None,
    q: queue.Queue,
    errors: list,
) -> None:
    from .doc_parser import parse_doc_file
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(parse_doc_file, abs_p): (root, rel)
            for (root, rel), abs_p in to_process_docs.items()
        }
        for future in as_completed(futures):
            root, rel = futures[future]
            try:
                sections = future.result()
                q.put((_KIND_DOC, sections, root, rel))
            except Exception as e:
                errors.append(f"parse {Path(root) / rel}: {e}")
    q.put(None)  # sentinel


def _flush_code_batch(
    pending: list,
    db_path: Path,
    device: str,
    precision: str,
    batch_size: int,
) -> int:
    from .database import insert_code_chunks_batch
    from .embedder import embed
    stored = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        embeddings = embed([c.code_text for c in batch], device=device, precision=precision)
        insert_code_chunks_batch(db_path, batch, embeddings)
        stored += len(batch)
    return stored


def _flush_doc_batch(
    pending: list,
    ddb_path: Path,
    device: str,
    precision: str,
    batch_size: int,
) -> int:
    from .database import insert_doc_sections_batch
    from .embedder import embed
    stored = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        embeddings = embed([s.content for s in batch], device=device, precision=precision)
        insert_doc_sections_batch(ddb_path, batch, embeddings)
        stored += len(batch)
    return stored


def _consume_and_embed(
    q: queue.Queue,
    num_producers: int,
    db_path: Path | None,
    ddb_path: Path | None,
    device: str,
    precision: str,
    batch_size: int,
) -> tuple[int, int, set, set]:
    """Drain the producer queue, embed, and write to DB with periodic checkpointing.

    Returns (code_stored, docs_stored, successful_code, successful_docs).
    """
    pending_code: list = []
    pending_doc: list = []
    successful_code: set[tuple[str, str]] = set()
    successful_docs: set[tuple[str, str]] = set()
    code_stored = 0
    docs_stored = 0
    sentinels_seen = 0

    while sentinels_seen < num_producers:
        try:
            item = q.get(timeout=0.05)
        except queue.Empty:
            continue

        if item is None:
            sentinels_seen += 1
            continue

        kind, items, root, rel = item
        if kind == _KIND_CODE:
            pending_code.extend(items)
            successful_code.add((root, rel))
        else:
            pending_doc.extend(items)
            successful_docs.add((root, rel))

        if len(pending_code) >= _CHECKPOINT_SIZE:
            batch, pending_code = pending_code[:_CHECKPOINT_SIZE], pending_code[_CHECKPOINT_SIZE:]
            code_stored += _flush_code_batch(batch, db_path, device, precision, batch_size)

        if len(pending_doc) >= _CHECKPOINT_SIZE:
            batch, pending_doc = pending_doc[:_CHECKPOINT_SIZE], pending_doc[_CHECKPOINT_SIZE:]
            docs_stored += _flush_doc_batch(batch, ddb_path, device, precision, batch_size)

    # Drain remainders
    if pending_code:
        code_stored += _flush_code_batch(pending_code, db_path, device, precision, batch_size)
    if pending_doc:
        docs_stored += _flush_doc_batch(pending_doc, ddb_path, device, precision, batch_size)

    return code_stored, docs_stored, successful_code, successful_docs


@cli.command()
@click.option("-i", "--input", "input_dirs", multiple=True, required=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Input directory (code and/or docs); repeatable")
@click.option("-o", "--output", required=True, help="Database name, e.g. my-project")
@click.option("--device", default="auto", show_default=True,
              type=click.Choice(["auto", "cpu", "cuda"]),
              help="Embedding device: auto detects CUDA and falls back to CPU")
@click.option("--limit-cpu", default=None, type=int,
              help="Max CPU cores for parallel chunking (default: all available cores)")
@click.option("--batch-size", "batch_size", default=None, type=int,
              help="Embedding batch size (default: 256 for CPU, 1024 for CUDA)")
@click.option("--force", is_flag=True,
              help="Force full rebuild, ignoring incremental state")
def prepare(input_dirs: tuple[Path, ...], output: str, device: str, limit_cpu: int | None, batch_size: int | None, force: bool):
    """Parse, embed, and store code and/or docs into a named database.

    Each -i directory is scanned automatically: .c/.h/.cpp files go into code.db,
    .pdf/.html/.htm files go into docs.db. Pass -i multiple times to combine
    directories.

    On re-run, only changed files are re-embedded. Use --force to rebuild
    everything from scratch.
    """
    from .embedder import default_batch_size, resolve_device

    if limit_cpu is not None and limit_cpu > (os.cpu_count() or 1):
        click.echo(
            f"Error: --limit-cpu={limit_cpu} exceeds available cores ({os.cpu_count()}).",
            err=True,
        )
        sys.exit(1)

    try:
        resolved_device = resolve_device(device)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if batch_size is None:
        batch_size = default_batch_size(resolved_device)

    precision = "float16" if resolved_device == "cuda" else "float32"

    click.echo(f"[prepare] device={resolved_device}  batch-size={batch_size}  precision={precision}")

    out_dir = CACHE_DIR / output
    out_dir.mkdir(parents=True, exist_ok=True)

    # Group files by their input directory (needed for manifest rel_path computation)
    code_by_dir: dict[Path, list[Path]] = {}
    doc_by_dir: dict[Path, list[Path]] = {}

    for d in input_dirs:
        code_files, doc_files = _detect_input_type(d)
        if code_files:
            click.echo(f"[code] {d} — {len(code_files)} .c/.h/.cpp file(s)")
            code_by_dir[d] = code_files
        if doc_files:
            click.echo(f"[docs] {d} — {len(doc_files)} .pdf/.html file(s)")
            doc_by_dir[d] = doc_files
        if not code_files and not doc_files:
            click.echo(f"[warn] {d} — no .c/.h/.cpp or .pdf/.html files found, skipping")

    all_code_files = [f for files in code_by_dir.values() for f in files]
    all_doc_files = [f for files in doc_by_dir.values() for f in files]

    if not all_code_files and not all_doc_files:
        click.echo("No .c/.h/.cpp or .pdf/.html files found in any input directory.", err=True)
        sys.exit(1)

    _logger.info("prepare: %d code file(s), %d doc file(s)", len(all_code_files), len(all_doc_files))

    db_path: Path | None = None
    ddb_path: Path | None = None
    to_process: dict[tuple[str, str], Path] = {}
    to_process_docs: dict[tuple[str, str], Path] = {}
    code_changed = False
    docs_changed = False

    # ── Code delta computation ─────────────────────────────────────────────
    if all_code_files:
        from .database import (
            delete_chunks_for_file, init_code_db,
            load_manifest, upsert_manifest_row, delete_manifest_row,
        )

        db_path = out_dir / "code.db"
        if force and db_path.exists():
            db_path.unlink()
        init_code_db(db_path)

        walk: dict[tuple[str, str], float] = {}
        for d, files in code_by_dir.items():
            root = str(d.resolve())
            for f in files:
                walk[(root, str(f.relative_to(d)))] = f.stat().st_mtime

        manifest = load_manifest(db_path)

        if manifest and not force:
            stored_roots = {r for (r, _) in manifest}
            current_roots = {r for (r, _) in walk}
            if stored_roots != current_roots:
                click.echo(
                    "Error: -i roots differ from those stored in the manifest. "
                    "Use --force to rebuild from scratch.", err=True
                )
                sys.exit(1)

        for (root, rel) in set(manifest) - set(walk):
            delete_chunks_for_file(db_path, str(Path(root) / rel))
            delete_manifest_row(db_path, rel, root)
            code_changed = True

        for (root, rel) in set(walk) - set(manifest):
            to_process[(root, rel)] = Path(root) / rel

        for (root, rel) in set(walk) & set(manifest):
            curr_mtime = walk[(root, rel)]
            stored_mtime, stored_sha = manifest[(root, rel)]
            if curr_mtime != stored_mtime:
                abs_p = Path(root) / rel
                if _sha256(abs_p) != stored_sha:
                    delete_chunks_for_file(db_path, str(abs_p))
                    to_process[(root, rel)] = abs_p
                else:
                    upsert_manifest_row(db_path, rel, root, curr_mtime, stored_sha)

        if to_process:
            code_changed = True

    # ── Docs delta computation ─────────────────────────────────────────────
    if all_doc_files:
        from .database import (
            delete_sections_for_source, init_docs_db,
            load_manifest, upsert_manifest_row, delete_manifest_row,
        )

        ddb_path = out_dir / "docs.db"
        if force and ddb_path.exists():
            ddb_path.unlink()
        init_docs_db(ddb_path)

        walk_docs: dict[tuple[str, str], float] = {}
        for d, files in doc_by_dir.items():
            root = str(d.resolve())
            for f in files:
                walk_docs[(root, str(f.relative_to(d)))] = f.stat().st_mtime

        manifest_docs = load_manifest(ddb_path)

        if manifest_docs and not force:
            stored_roots = {r for (r, _) in manifest_docs}
            current_roots = {r for (r, _) in walk_docs}
            if stored_roots != current_roots:
                click.echo(
                    "Error: -i roots differ from those stored in the manifest. "
                    "Use --force to rebuild from scratch.", err=True
                )
                sys.exit(1)

        for (root, rel) in set(manifest_docs) - set(walk_docs):
            delete_sections_for_source(ddb_path, str(Path(root) / rel))
            delete_manifest_row(ddb_path, rel, root)
            docs_changed = True

        for (root, rel) in set(walk_docs) - set(manifest_docs):
            to_process_docs[(root, rel)] = Path(root) / rel

        for (root, rel) in set(walk_docs) & set(manifest_docs):
            curr_mtime = walk_docs[(root, rel)]
            stored_mtime, stored_sha = manifest_docs[(root, rel)]
            if curr_mtime != stored_mtime:
                abs_p = Path(root) / rel
                if _sha256(abs_p) != stored_sha:
                    delete_sections_for_source(ddb_path, str(abs_p))
                    to_process_docs[(root, rel)] = abs_p
                else:
                    upsert_manifest_row(ddb_path, rel, root, curr_mtime, stored_sha)

        if to_process_docs:
            docs_changed = True

    # ── Concurrent parse → embed → checkpoint ─────────────────────────────
    num_producers = (1 if to_process else 0) + (1 if to_process_docs else 0)

    if num_producers > 0:
        q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        producer_errors: list[str] = []
        threads = []

        if to_process:
            t = threading.Thread(
                target=_run_code_producer,
                args=(to_process, limit_cpu, q, producer_errors),
                daemon=True,
            )
            t.start()
            threads.append(t)

        if to_process_docs:
            t = threading.Thread(
                target=_run_doc_producer,
                args=(to_process_docs, limit_cpu, q, producer_errors),
                daemon=True,
            )
            t.start()
            threads.append(t)

        click.echo(f"[prepare] parsing {len(to_process)} code file(s) + {len(to_process_docs)} doc file(s) concurrently...")

        code_stored, docs_stored, successful_code, successful_docs = _consume_and_embed(
            q, num_producers, db_path, ddb_path, resolved_device, precision, batch_size
        )

        for t in threads:
            t.join()

        for msg in producer_errors:
            click.echo(f"  Warning: {msg}", err=True)

        # Batch-write manifests for all successfully processed files
        if successful_code and db_path:
            from .database import upsert_manifest_rows_batch
            rows = [
                (rel, root, to_process[(root, rel)].stat().st_mtime, _sha256(to_process[(root, rel)]))
                for (root, rel) in successful_code
            ]
            upsert_manifest_rows_batch(db_path, rows)
            click.echo(f"  {code_stored} code chunks → {db_path}")
            _logger.info("prepare: stored %d code chunks in %s", code_stored, db_path)

        if successful_docs and ddb_path:
            from .database import upsert_manifest_rows_batch
            rows = [
                (rel, root, to_process_docs[(root, rel)].stat().st_mtime, _sha256(to_process_docs[(root, rel)]))
                for (root, rel) in successful_docs
            ]
            upsert_manifest_rows_batch(ddb_path, rows)
            click.echo(f"  {docs_stored} doc sections → {ddb_path}")
            _logger.info("prepare: stored %d doc sections in %s", docs_stored, ddb_path)

    if not code_changed:
        click.echo("[prepare] nothing changed (code)")
    if not docs_changed:
        click.echo("[prepare] nothing changed (docs)")

    version_cfg = {"embedding_model": "all-MiniLM-L6-v2"}
    with open(out_dir / "config.json", "w") as f:
        json.dump(version_cfg, f, indent=2)

    cfg = load_global()
    cfg["active_version"] = output
    save_global(cfg)
    click.echo(f"Active version set to '{output}'.")


# ---------------------------------------------------------------------------
# SEARCH — Query indexes locally
# ---------------------------------------------------------------------------

class _SearchGroup(click.Group):
    """A Click Group that routes unknown leading tokens to the group callback.

    Click puts the first non-option token in ``_protected_args`` and tries to
    resolve it as a subcommand, raising UsageError for unrecognised tokens.
    This subclass moves unrecognised first tokens back into ``ctx.args`` so
    Click's ``invoke_without_command`` path runs the group callback instead.
    Registered subcommands (``code``, ``docs``, ``symbol``) route normally.
    """

    def invoke(self, ctx: click.Context) -> object:
        all_args = [*ctx._protected_args, *ctx.args]
        if all_args and all_args[0] not in self.commands:
            ctx.args = all_args
            ctx._protected_args = []
        return super().invoke(ctx)


@cli.group("search", cls=_SearchGroup, invoke_without_command=True,
           context_settings={"allow_extra_args": True, "allow_interspersed_args": False})
@click.option("--top-k", default=5, show_default=True, help="Number of results to return")
@click.pass_context
def search(ctx, top_k: int):
    """Search code and/or docs. Without a subcommand, searches all three."""
    if ctx.invoked_subcommand is not None:
        return

    if not ctx.args:
        click.echo(ctx.get_help())
        sys.exit(0)

    query = " ".join(ctx.args)

    # Search all three: code, docs, symbol (if exact match)
    from .database import search_code as db_search_code, search_docs as db_search_docs, get_symbol as db_get_symbol
    from .embedder import embed_one

    found_any = False

    # Try exact symbol match first
    code_db = code_db_path()
    if code_db and code_db.exists():
        result = db_get_symbol(code_db, query)
        if result is not None:
            click.echo(f"\n[SYMBOL] {result['symbol_name']}  ({result['type']})")
            click.echo(f"File   : {result['file_path']}:{result['line_start']}-{result['line_end']}")
            click.echo(f"\n{result['code_text']}")
            found_any = True

    # Search code
    if code_db and code_db.exists():
        q_emb = embed_one(query)
        results = db_search_code(code_db, q_emb, top_k=top_k)
        if results:
            if found_any:
                click.echo("\n" + "="*70)
            click.echo("\n[CODE]")
            for i, r in enumerate(results, 1):
                click.echo(
                    f"[{i}] {r['symbol_name']}  ({r['type']})  score={r['similarity_score']}\n"
                    f"    {r['file_path']}:{r['line_start']}-{r['line_end']}"
                )
            found_any = True

    # Search docs
    docs_db = docs_db_path()
    if docs_db and docs_db.exists():
        q_emb = embed_one(query)
        results = db_search_docs(docs_db, q_emb, top_k=top_k)
        if results:
            if found_any:
                click.echo("\n" + "="*70)
            click.echo("\n[DOCS]")
            for i, r in enumerate(results, 1):
                tags = ", ".join(r["feature_tags"]) if r["feature_tags"] else ""
                page = f"  p.{r['page_range']}" if r["page_range"] else ""
                click.echo(
                    f"[{i}] {r['title']}  score={r['similarity_score']}{page}\n"
                    f"    Tags: {tags}"
                )
            found_any = True

    if not found_any:
        click.echo("No results found in code or docs.")
        sys.exit(1)


@search.command("code")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results to return")
def search_code(query: str, top_k: int):
    """Semantic search over indexed code chunks."""
    from .database import search_code as db_search
    from .embedder import embed_one

    db = code_db_path()
    if db is None:
        click.echo("No active version set. Run `qrag mcp active <version>`.", err=True)
        sys.exit(1)
    if not db.exists():
        click.echo(f"code.db not found at {db}. Run `qrag prepare` first.", err=True)
        sys.exit(1)

    _logger.debug("search-code: query=%r top_k=%d db=%s", query, top_k, db)
    q_emb = embed_one(query)
    results = db_search(db, q_emb, top_k=top_k)
    _logger.info("search-code: %d result(s) for query=%r", len(results), query)

    if not results:
        click.echo("No results found.")
        return

    for i, r in enumerate(results, 1):
        click.echo(
            f"\n[{i}] {r['symbol_name']}  ({r['type']})  score={r['similarity_score']}\n"
            f"    {r['file_path']}:{r['line_start']}-{r['line_end']}\n"
            f"    {r['code_snippet'][:120].replace(chr(10), ' ')}"
        )



@search.command("docs")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results to return")
def search_docs(query: str, top_k: int):
    """Semantic search over indexed documentation sections."""
    from .database import search_docs as db_search
    from .embedder import embed_one

    db = docs_db_path()
    if db is None:
        click.echo("No active version set. Run `qrag mcp active <version>`.", err=True)
        sys.exit(1)
    if not db.exists():
        click.echo(f"docs.db not found at {db}. Run `qrag prepare -i <docs_dir>` first.", err=True)
        sys.exit(1)

    _logger.debug("search-docs: query=%r top_k=%d db=%s", query, top_k, db)
    q_emb = embed_one(query)
    results = db_search(db, q_emb, top_k=top_k)
    _logger.info("search-docs: %d result(s) for query=%r", len(results), query)

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



@search.command("symbol")
@click.argument("name")
def search_symbol(name: str):
    """Look up exact symbol definition by name."""
    from .database import get_symbol as db_get_symbol

    db = code_db_path()
    if db is None:
        click.echo("No active version set. Run `qrag mcp active <version>`.", err=True)
        sys.exit(1)
    if not db.exists():
        click.echo(f"code.db not found at {db}. Run `qrag prepare` first.", err=True)
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
# HUB — Share & manage indexes via GitHub
# ---------------------------------------------------------------------------

@cli.group("hub")
def hub():
    """Manage and share indexes via GitHub."""


@hub.command("list")
def hub_list():
    """List available versions on the configured repository."""
    url = repo_url()
    if not url:
        click.echo("Error: No repo URL configured. Set it with environment or config.", err=True)
        sys.exit(1)

    from .github_distribution import list_databases as gh_list
    gh_list(url)


@hub.command("download")
@click.argument("version")
def hub_download(version: str):
    """Download a version database from the repository."""
    url = repo_url()
    if not url:
        click.echo("Error: No repo URL configured. Set it with environment or config.", err=True)
        sys.exit(1)

    from .github_distribution import download_database
    download_database(url, version, CACHE_DIR)

    cfg = load_global()
    cfg["active_version"] = version
    save_global(cfg)
    click.echo(f"Active version set to '{version}'.")


@hub.command("push")
@click.argument("version")
@click.option("--force", is_flag=True, help="Overwrite existing release")
def hub_push(version: str, force: bool):
    """Push version databases to the repository."""
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


@hub.command("delete")
@click.argument("version")
def hub_delete(version: str):
    """Delete a local version database."""
    version_dir = CACHE_DIR / version
    from .github_distribution import delete_database
    delete_database(version_dir)
