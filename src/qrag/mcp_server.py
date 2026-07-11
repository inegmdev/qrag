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

# Session-scoped database selection (AD-17). Lives only in this process's
# memory: stdio MCP transport spawns one server process per agent session,
# so the process boundary already is the session boundary — no session-ID
# scheme is needed. `_session_dbs=None` means "use the full global active
# set"; a non-None value is a user-narrowed subset of it.
_session_dbs: list[str] | None = None
_session_scoped: bool = False


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


def _global_active_versions() -> list[str]:
    """The durable, CLI-managed candidate pool (`qrag ai active ...`)."""
    cfg = load_global()
    return cfg.get("active_versions", [])


def _effective_versions() -> list[str]:
    """Session-narrowed subset if set, else the full global active set."""
    global_versions = _global_active_versions()
    if _session_dbs is None:
        return global_versions
    return [v for v in _session_dbs if v in global_versions]


def _excluded_active_dbs() -> list[str]:
    """Globally active versions currently excluded by session narrowing."""
    if _session_dbs is None:
        return []
    global_versions = _global_active_versions()
    return [v for v in global_versions if v not in _session_dbs]


def _scope_meta() -> dict:
    """Fields appended to search results: fallback-suggestion + first-use nudge.

    The server does no relevance matching of its own (AD-17) — it only
    surfaces which globally active DBs are excluded from the current
    session; the skill instructs the LLM to judge relevance itself.
    """
    meta: dict = {}
    excluded = _excluded_active_dbs()
    if excluded:
        meta["excluded_active_dbs"] = excluded
    if not _session_scoped:
        global_versions = _global_active_versions()
        if len(global_versions) > 1:
            meta["scope_hint"] = (
                f"Session not yet scoped — {len(global_versions)} databases "
                "available via list_databases()"
            )
    return meta


def _get_active_dbs() -> tuple[list[Path], list[Path]]:
    """Return (code_dbs, docs_dbs) for all effective versions that exist on disk."""
    versions = _effective_versions()
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


def list_databases_impl() -> list[dict]:
    """List the globally active databases, for checklist rendering by the LLM."""
    result = []
    for v in _global_active_versions():
        code_path = CACHE_DIR / v / "code.db"
        docs_path = CACHE_DIR / v / "docs.db"
        has_code = code_path.exists()
        has_docs = docs_path.exists()
        size_bytes = (code_path.stat().st_size if has_code else 0) + (
            docs_path.stat().st_size if has_docs else 0
        )
        result.append(
            {
                "version": v,
                "has_code": has_code,
                "has_docs": has_docs,
                "size_bytes": size_bytes,
            }
        )
    return result


def set_active_databases_impl(versions: list[str]) -> dict:
    """Narrow the current session to a subset of the globally active DBs."""
    global _session_dbs, _session_scoped

    if not versions:
        raise ValueError("versions must be a non-empty list")

    global_versions = _global_active_versions()
    unknown = [v for v in versions if v not in global_versions]
    if unknown:
        raise ValueError(
            f"Unknown version(s) not in the globally active set: {unknown}. "
            f"Globally active versions: {global_versions}"
        )

    _session_dbs = list(dict.fromkeys(versions))  # dedupe, preserve order
    _session_scoped = True
    return {"active_databases": _session_dbs}


def reset_active_databases_impl() -> dict:
    """Clear the session narrowing, reverting to the full global active set."""
    global _session_dbs, _session_scoped
    _session_dbs = None
    _session_scoped = True
    return {"active_databases": _global_active_versions()}


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


def search_code_impl(query: str) -> dict:
    """Semantic search across all session-scoped active code databases."""
    code_dbs, _ = _get_active_dbs()
    if not code_dbs:
        return {"results": [], **_scope_meta()}

    q_emb = embed_one(query)
    all_results: list[dict] = []

    with ThreadPoolExecutor(max_workers=min(len(code_dbs), 8)) as pool:
        futures = {pool.submit(db_search_code, db, q_emb, 10): db for db in code_dbs}
        for fut in as_completed(futures):
            try:
                all_results.extend(fut.result())
            except Exception as e:
                _log_error(f"search_code fan-out error ({futures[fut]}): {e}")

    return {"results": _merge_code(all_results, top_k=10), **_scope_meta()}


def search_docs_impl(query: str) -> dict:
    """Semantic search across all session-scoped active docs databases."""
    _, docs_dbs = _get_active_dbs()
    if not docs_dbs:
        return {"results": [], **_scope_meta()}

    q_emb = embed_one(query)
    all_results: list[dict] = []

    with ThreadPoolExecutor(max_workers=min(len(docs_dbs), 8)) as pool:
        futures = {pool.submit(db_search_docs, db, q_emb, 10): db for db in docs_dbs}
        for fut in as_completed(futures):
            try:
                all_results.extend(fut.result())
            except Exception as e:
                _log_error(f"search_docs fan-out error ({futures[fut]}): {e}")

    return {"results": _merge_docs(all_results, top_k=10), **_scope_meta()}


def get_symbol_definition_impl(symbol: str) -> dict:
    """Get the exact definition of a symbol, searching session-scoped active code databases."""
    code_dbs, _ = _get_active_dbs()
    if not code_dbs:
        return {"error": "No active code databases found", **_scope_meta()}

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
                **_scope_meta(),
            }

    return {"error": f"Symbol '{symbol}' not found", **_scope_meta()}


def list_symbols_impl(pattern: str = "", limit: int = 200) -> dict:
    """List symbols across session-scoped active code databases, deduplicated by name."""
    code_dbs, _ = _get_active_dbs()
    if not code_dbs:
        return {"symbols": [], **_scope_meta()}

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

    return {"symbols": merged, **_scope_meta()}


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
    "list_databases": {
        "description": "List the globally active databases (set via `qrag ai active`) available to select from for this session. Call this before rendering a database-selection checklist to the user, at the start of a conversation or when the user asks to change search scope.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "impl": list_databases_impl,
    },
    "set_active_databases": {
        "description": "Narrow search to a subset of the globally active databases for the rest of this session only (does not change the user's global `qrag ai active` configuration). Must be a non-empty list of versions returned by list_databases; unknown versions are rejected.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "versions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Versions to activate for this session, chosen from list_databases output",
                }
            },
            "required": ["versions"],
        },
        "impl": set_active_databases_impl,
    },
    "reset_active_databases": {
        "description": "Clear any session-level database narrowing and revert to searching the full globally active set. Use when the user asks to search everything again.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "impl": reset_active_databases_impl,
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
