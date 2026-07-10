"""Unit tests for mcp_server.py session-scoped database selection (AD-17)."""
import json

import pytest

import qrag.mcp_server as mcp_server
from qrag.config import save_global


@pytest.fixture
def scoped_env(isolated_qrag, monkeypatch):
    """Point mcp_server at the isolated cache dir and reset session state."""
    monkeypatch.setattr(mcp_server, "CACHE_DIR", isolated_qrag)
    monkeypatch.setattr(mcp_server, "_session_dbs", None)
    monkeypatch.setattr(mcp_server, "_session_scoped", False)
    return isolated_qrag


def _make_version(cache_dir, version, code=True, docs=True):
    d = cache_dir / version
    d.mkdir(parents=True, exist_ok=True)
    if code:
        (d / "code.db").write_bytes(b"x" * 10)
    if docs:
        (d / "docs.db").write_bytes(b"y" * 20)


def _set_global_active(versions):
    save_global({"active_versions": versions})


# ---------------------------------------------------------------------------
# list_databases_impl
# ---------------------------------------------------------------------------


def test_list_databases_reports_global_active_only(scoped_env):
    _make_version(scoped_env, "v1")
    _make_version(scoped_env, "v2", docs=False)
    _make_version(scoped_env, "unrelated")  # downloaded but not globally active
    _set_global_active(["v1", "v2"])

    result = mcp_server.list_databases_impl()

    names = {r["version"] for r in result}
    assert names == {"v1", "v2"}
    v2 = next(r for r in result if r["version"] == "v2")
    assert v2["has_code"] is True
    assert v2["has_docs"] is False


# ---------------------------------------------------------------------------
# set_active_databases_impl
# ---------------------------------------------------------------------------


def test_set_active_databases_narrows_effective_versions(scoped_env):
    _make_version(scoped_env, "v1")
    _make_version(scoped_env, "v2")
    _set_global_active(["v1", "v2"])

    result = mcp_server.set_active_databases_impl(["v1"])

    assert result == {"active_databases": ["v1"]}
    assert mcp_server._effective_versions() == ["v1"]
    assert mcp_server._session_scoped is True


def test_set_active_databases_rejects_empty_list(scoped_env):
    _set_global_active(["v1"])
    with pytest.raises(ValueError):
        mcp_server.set_active_databases_impl([])


def test_set_active_databases_rejects_unknown_version(scoped_env):
    _set_global_active(["v1"])
    with pytest.raises(ValueError):
        mcp_server.set_active_databases_impl(["v1", "does-not-exist"])
    # rejected call must not mutate session state
    assert mcp_server._session_dbs is None


# ---------------------------------------------------------------------------
# reset_active_databases_impl
# ---------------------------------------------------------------------------


def test_reset_active_databases_reverts_to_full_global_set(scoped_env):
    _make_version(scoped_env, "v1")
    _make_version(scoped_env, "v2")
    _set_global_active(["v1", "v2"])
    mcp_server.set_active_databases_impl(["v1"])

    result = mcp_server.reset_active_databases_impl()

    assert result == {"active_databases": ["v1", "v2"]}
    assert mcp_server._effective_versions() == ["v1", "v2"]


# ---------------------------------------------------------------------------
# _scope_meta: excluded_active_dbs + scope_hint
# ---------------------------------------------------------------------------


def test_scope_meta_excludes_narrowed_out_versions(scoped_env):
    _set_global_active(["v1", "v2", "v3"])
    mcp_server.set_active_databases_impl(["v1"])

    meta = mcp_server._scope_meta()

    assert meta["excluded_active_dbs"] == ["v2", "v3"]
    assert "scope_hint" not in meta  # already scoped, no nudge


def test_scope_meta_hints_when_unscoped_and_multiple_dbs(scoped_env):
    _set_global_active(["v1", "v2"])

    meta = mcp_server._scope_meta()

    assert "scope_hint" in meta
    assert "excluded_active_dbs" not in meta


def test_scope_meta_no_hint_for_single_global_db(scoped_env):
    _set_global_active(["v1"])

    meta = mcp_server._scope_meta()

    assert meta == {}


# ---------------------------------------------------------------------------
# handle_request wiring for the new tools
# ---------------------------------------------------------------------------


def test_tools_list_includes_new_scoping_tools(scoped_env):
    response = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in response["result"]["tools"]}
    assert {"list_databases", "set_active_databases", "reset_active_databases"} <= names


def test_tools_call_set_active_databases_via_handle_request(scoped_env):
    _make_version(scoped_env, "v1")
    _set_global_active(["v1"])

    response = mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "set_active_databases", "arguments": {"versions": ["v1"]}},
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload == {"active_databases": ["v1"]}


def test_tools_call_unknown_version_surfaces_as_jsonrpc_error(scoped_env):
    _set_global_active(["v1"])

    response = mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "set_active_databases", "arguments": {"versions": ["ghost"]}},
        }
    )

    assert "error" in response
    assert response["error"]["code"] == -32603
