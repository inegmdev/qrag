"""MCP server for raghub.

Implements the Model Context Protocol over JSON-RPC / stdio.
"""

import json
import sys
from pathlib import Path

from .config import load_global, CACHE_DIR
from .database import search_code as db_search_code, search_docs as db_search_docs, get_symbol as db_get_symbol, list_symbols as db_list_symbols
from .embedder import embed_one


def _ensure_active_version() -> tuple[Path, Path]:
    """Ensure an active version is set and return code_db, docs_db paths."""
    cfg = load_global()
    active = cfg.get("active_version")
    if not active:
        raise RuntimeError("No active version set. Run `raghub mcp active <version>` first.")

    code_db = CACHE_DIR / active / "code.db"
    docs_db = CACHE_DIR / active / "docs.db"

    if not code_db.exists() and not docs_db.exists():
        raise RuntimeError(
            f"No databases found for version '{active}'. "
            f"Expected: {code_db} or {docs_db}"
        )

    return code_db, docs_db


def search_code_impl(query: str) -> list[dict]:
    """Semantic search across indexed code chunks."""
    code_db, _ = _ensure_active_version()
    if not code_db.exists():
        return []

    q_emb = embed_one(query)
    results = db_search_code(code_db, q_emb, top_k=10)
    return results


def search_docs_impl(query: str) -> list[dict]:
    """Semantic search across indexed documentation sections."""
    _, docs_db = _ensure_active_version()
    if not docs_db.exists():
        return []

    q_emb = embed_one(query)
    results = db_search_docs(docs_db, q_emb, top_k=10)
    return results


def get_symbol_definition_impl(symbol: str) -> dict:
    """Get the exact definition of a symbol."""
    code_db, _ = _ensure_active_version()
    if not code_db.exists():
        return {"error": "Code database not found"}

    result = db_get_symbol(code_db, symbol)
    if result is None:
        return {"error": f"Symbol '{symbol}' not found"}

    return {
        "symbol_name": result["symbol_name"],
        "type": result["type"],
        "file_path": result["file_path"],
        "line_start": result["line_start"],
        "line_end": result["line_end"],
        "code": result["code_text"],
    }


def list_symbols_impl(pattern: str = "", limit: int = 200) -> list[dict]:
    """List indexed symbols, optionally filtered by pattern."""
    code_db, _ = _ensure_active_version()
    if not code_db.exists():
        return []

    results = db_list_symbols(code_db, pattern, limit)
    return results


# Tool definitions for MCP
TOOLS = {
    "search_code": {
        "description": "Search indexed source code (C/H files) by meaning. Use when asked about driver implementations, API usage, how something works in code, or any question about SDK functions and structures.",
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
                    "name": "raghub",
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
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            # Only respond if this is not a notification (has an id)
            if request.get("id") is not None:
                print(json.dumps(response))
                sys.stdout.flush()
        except json.JSONDecodeError:
            continue
        except Exception as e:
            continue


if __name__ == "__main__":
    run()
