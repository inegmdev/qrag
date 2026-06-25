"""MCP server for qrag.

Implements the Model Context Protocol over JSON-RPC / stdio.
"""

import datetime
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import load_global, CACHE_DIR
from .database import search_code as db_search_code, search_docs as db_search_docs, get_symbol as db_get_symbol, list_symbols as db_list_symbols
from .embedder import embed_one

_LOG_DIR = Path.home() / ".qrag" / "logs"


def _log_error(message: str) -> None:
    """Append an error entry to ~/.qrag/logs/mcp_errors.log (never raises)."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        with open(_LOG_DIR / "mcp_errors.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _error_response(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _get_active_dbs() -> tuple[list[Path], list[Path]]:
    """Return (code_dbs, docs_dbs) for all active versions that exist on disk."""
    cfg = load_global()
    versions = cfg.get("active_versions", [])
    if not versions:
        raise RuntimeError(
            "No active versions set. Run `qrag ai active <version>` first."
        )

    code_dbs = [p for v in versions if (p := CACHE_DIR / v / "code.db").exists()]
    docs_dbs = [p for v in versions if (p := CACHE_DIR / v / "docs.db").exists()]

    if not code_dbs and not docs_dbs:
        raise RuntimeError(
            f"No databases found for active versions: {versions}. "
            "Download them first with `qrag hub download <version>`."
        )

    return code_dbs, docs_dbs


def _merge_code(all_results: list[dict], top_k: int) -> list[dict]:
    """Sort by score, deduplicate by (file_path, line_start), return top_k."""
    all_results.sort(key=lambda r: r.get("similarity_score", 0), reverse=True)
    seen: set[tuple] = set()
    merged = []
    for r in all_results:
        key = (r.get("file_path"), r.get("line_start"))
        if key not in seen:
            seen.add(key)
            merged.append(r)
        if len(merged) >= top_k:
            break
    return merged


def _merge_docs(all_results: list[dict], top_k: int) -> list[dict]:
    """Sort by score, deduplicate by (source_path, page_range), return top_k."""
    all_results.sort(key=lambda r: r.get("similarity_score", 0), reverse=True)
    seen: set[tuple] = set()
    merged = []
    for r in all_results:
        key = (r.get("source_path"), r.get("page_range"))
        if key not in seen:
            seen.add(key)
            merged.append(r)
        if len(merged) >= top_k:
            break
    return merged


def search_code_impl(query: str) -> list[dict]:
    """Semantic search across all active code databases."""
    code_dbs, _ = _get_active_dbs()
    if not code_dbs:
        return []

    q_emb = embed_one(query)
    all_results: list[dict] = []

    with ThreadPoolExecutor(max_workers=min(len(code_dbs), 8)) as pool:
        futures = {pool.submit(db_search_code, db, q_emb, 10): db for db in code_dbs}
        for fut in as_completed(futures):
            try:
                all_results.extend(fut.result())
            except Exception as e:
                _log_error(f"search_code fan-out error ({futures[fut]}): {e}")

    return _merge_code(all_results, top_k=10)


def search_docs_impl(query: str) -> list[dict]:
    """Semantic search across all active docs databases."""
    _, docs_dbs = _get_active_dbs()
    if not docs_dbs:
        return []

    q_emb = embed_one(query)
    all_results: list[dict] = []

    with ThreadPoolExecutor(max_workers=min(len(docs_dbs), 8)) as pool:
        futures = {pool.submit(db_search_docs, db, q_emb, 10): db for db in docs_dbs}
        for fut in as_completed(futures):
            try:
                all_results.extend(fut.result())
            except Exception as e:
                _log_error(f"search_docs fan-out error ({futures[fut]}): {e}")

    return _merge_docs(all_results, top_k=10)


def get_symbol_definition_impl(symbol: str) -> dict:
    """Get the exact definition of a symbol, searching all active code databases."""
    code_dbs, _ = _get_active_dbs()
    if not code_dbs:
        return {"error": "No active code databases found"}

    for code_db in code_dbs:
        result = db_get_symbol(code_db, symbol)
        if result is not None:
            return {
                "symbol_name": result["symbol_name"],
                "type": result["type"],
                "file_path": result["file_path"],
                "line_start": result["line_start"],
                "line_end": result["line_end"],
                "code": result["code_text"],
            }

    return {"error": f"Symbol '{symbol}' not found"}


def list_symbols_impl(pattern: str = "", limit: int = 200) -> list[dict]:
    """List symbols across all active code databases, deduplicated by name."""
    code_dbs, _ = _get_active_dbs()
    if not code_dbs:
        return []

    all_results: list[dict] = []
    for code_db in code_dbs:
        all_results.extend(db_list_symbols(code_db, pattern, limit))

    seen: set[str] = set()
    merged = []
    for r in all_results:
        name = r.get("symbol_name", "")
        if name not in seen:
            seen.add(name)
            merged.append(r)
        if len(merged) >= limit:
            break

    return merged


# Tool definitions for MCP
TOOLS = {
    "search_code": {
        "description": "Search indexed source code (C/C++ files) by meaning. Use when asked about implementations, API usage, how something works in code, or any question about functions and structures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text"}
            },
            "required": ["query"],
        },
        "impl": search_code_impl,
    },
    "search_docs": {
        "description": "Search indexed documentation sections (PDF/HTML). Use when asked about hardware specs, configuration guides, architecture details, registers, memory maps, or any question answerable from docs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text"}
            },
            "required": ["query"],
        },
        "impl": search_docs_impl,
    },
    "get_symbol_definition": {
        "description": "Look up the exact source definition of a symbol (function, struct, typedef, or macro) by its precise name. Use when you know the symbol name and need its signature, fields, or implementation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Exact symbol name"}
            },
            "required": ["symbol"],
        },
        "impl": get_symbol_definition_impl,
    },
    "list_symbols": {
        "description": "List symbols (functions, structs, macros) indexed from source code, optionally filtered by a name pattern. Use to discover what is available before searching.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Optional substring to filter symbol names",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of symbols to return (default: 200)",
                    "default": 200,
                },
            },
        },
        "impl": list_symbols_impl,
    },
}


def handle_request(request: dict) -> dict:
    """Handle a JSON-RPC 2.0 request."""
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    # Handle initialize request (MCP protocol handshake)
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "qrag",
                    "version": "0.1.0",
                },
            },
        }

    # Handle tools/list request
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": tool["description"],
                        "inputSchema": tool["inputSchema"],
                    }
                    for name, tool in TOOLS.items()
                ]
            },
        }

    # Handle tool calls
    if method == "tools/call":
        tool_name = params.get("name")
        tool_params = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        try:
            impl = TOOLS[tool_name]["impl"]
            result = impl(**tool_params)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result)}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def run():
    """Entry point for the MCP server - reads JSON-RPC from stdin, writes to stdout."""
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            req_id = None
            try:
                request = json.loads(line)
                req_id = request.get("id")
                response = handle_request(request)
                if req_id is not None:
                    print(json.dumps(response))
                    sys.stdout.flush()
            except json.JSONDecodeError as e:
                _log_error(f"Parse error on line: {line!r} — {e}")
                if req_id is not None:
                    print(json.dumps(_error_response(req_id, -32700, "Parse error: invalid JSON")))
                    sys.stdout.flush()
            except Exception as e:
                _log_error(f"Unhandled exception (id={req_id}): {traceback.format_exc()}")
                if req_id is not None:
                    print(json.dumps(_error_response(req_id, -32603, f"Internal error: {e}")))
                    sys.stdout.flush()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
    except Exception:
        _log_error(f"Fatal loop error: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    run()
