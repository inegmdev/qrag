"""Tests for the remote backend layer and remotes config.

Every test mocks the transport boundary (github_distribution / config), so no
network or `gh` CLI is touched.
"""
import datetime
import json

import pytest

from qrag import config, explore


# ---------------------------------------------------------------------------
# Registry + resolution
# ---------------------------------------------------------------------------

def test_github_registered():
    assert "github" in explore.REGISTRY
    assert explore.REGISTRY["github"] is explore.GitHubBackend
    assert explore.GitHubBackend.type == "github"


def test_get_backend_named(monkeypatch):
    monkeypatch.setattr(config, "get_remote",
                        lambda n: {"type": "github", "url": "https://github.com/o/r"} if n == "gh" else None)
    backend = explore.get_backend("gh")
    assert isinstance(backend, explore.GitHubBackend)
    assert backend.name == "gh"
    assert backend.url == "https://github.com/o/r"


def test_resolve_unknown_remote_raises(monkeypatch):
    monkeypatch.setattr(config, "get_remote", lambda n: None)
    with pytest.raises(explore.RemoteError, match="No remote named"):
        explore.resolve_remote("nope")


def test_resolve_default_remote(monkeypatch):
    monkeypatch.setattr(config, "default_remote",
                        lambda: ("default", {"type": "github", "url": "u"}))
    name, cfg = explore.resolve_remote()
    assert name == "default" and cfg["url"] == "u"


def test_resolve_falls_back_to_repo_url(monkeypatch):
    monkeypatch.setattr(config, "default_remote", lambda: None)
    monkeypatch.setattr(config, "repo_url", lambda: "https://github.com/o/legacy")
    name, cfg = explore.resolve_remote()
    assert name == "default"
    assert cfg == {"type": "github", "url": "https://github.com/o/legacy"}


def test_resolve_no_remote_raises(monkeypatch):
    monkeypatch.setattr(config, "default_remote", lambda: None)
    monkeypatch.setattr(config, "repo_url", lambda: None)
    with pytest.raises(explore.RemoteError, match="No remote configured"):
        explore.resolve_remote()


def test_unknown_remote_type_raises(monkeypatch):
    monkeypatch.setattr(config, "get_remote", lambda n: {"type": "s3", "url": "u"})
    with pytest.raises(explore.RemoteError, match="Unknown remote type 's3'"):
        explore.get_backend("x")


# ---------------------------------------------------------------------------
# GitHubBackend (mocked gh transport)
# ---------------------------------------------------------------------------

def test_github_list_versions_parses(monkeypatch):
    from qrag import github_distribution
    fake = [
        {"tagName": "v2", "name": "Database v2", "publishedAt": "2026-07-01T12:00:00Z"},
        {"tagName": "v1", "name": "Database v1", "publishedAt": "2026-06-01T09:30:00Z"},
    ]
    monkeypatch.setattr(github_distribution, "fetch_releases", lambda url: fake)
    backend = explore.GitHubBackend(url="https://github.com/o/r", name="default")
    versions = backend.list_versions()
    assert [v.name for v in versions] == ["v2", "v1"]
    assert versions[0].remote == "default"
    assert versions[0].url == "https://github.com/o/r/releases/tag/v2"
    assert isinstance(versions[0].updated_at, datetime.datetime)


def test_github_list_versions_wraps_error(monkeypatch):
    from qrag import github_distribution

    def boom(url):
        raise RuntimeError("gh exploded")

    monkeypatch.setattr(github_distribution, "fetch_releases", boom)
    backend = explore.GitHubBackend(url="u", name="default")
    with pytest.raises(explore.RemoteError, match="gh exploded"):
        backend.list_versions()


def test_github_check_auth_no_token(monkeypatch):
    from qrag import github_distribution
    monkeypatch.setattr(github_distribution, "_get_github_token", lambda: None)
    backend = explore.GitHubBackend(url="u", name="default")
    with pytest.raises(explore.RemoteError, match="No GitHub authentication"):
        backend.check_auth()


def test_github_check_auth_ok(monkeypatch):
    from qrag import github_distribution
    monkeypatch.setattr(github_distribution, "_get_github_token", lambda: "tok")
    explore.GitHubBackend(url="u", name="default").check_auth()  # no raise


# ---------------------------------------------------------------------------
# merge + origin tracking
# ---------------------------------------------------------------------------

def _vi(name, active=False):
    return explore.VersionInfo(
        name=name, path=None, has_code=True, has_docs=False, size_bytes=10,
        built_at=None, active=active, symbols=1, sections=0, docs=0, languages=[],
    )


def test_merge_versions():
    locals_ = [_vi("v1", active=True), _vi("v3")]
    remotes = [
        explore.RemoteVersion(name="v1", remote="default"),
        explore.RemoteVersion(name="v2", remote="default"),
    ]
    rows = {r.name: r for r in explore.merge_versions(locals_, remotes)}
    assert [r.name for r in explore.merge_versions(locals_, remotes)] == ["v1", "v2", "v3"]
    assert rows["v1"].location == "local+remote"
    assert rows["v2"].location == "remote"
    assert rows["v3"].location == "local"


def test_write_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(explore, "CACHE_DIR", tmp_path)
    (tmp_path / "v1").mkdir()
    (tmp_path / "v1" / "config.json").write_text('{"embedding_model": "m"}')
    explore.write_origin("v1", "hf-mirror")
    data = json.loads((tmp_path / "v1" / "config.json").read_text())
    assert data["origin_remote"] == "hf-mirror"
    assert data["origin_version"] == "v1"
    assert data["embedding_model"] == "m"  # preserved


# ---------------------------------------------------------------------------
# config: remotes registry + migration
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "GLOBAL_CONFIG", cfg_path)
    return cfg_path


def test_legacy_repo_url_migrates(temp_config):
    temp_config.write_text(json.dumps({"repo_url": "https://github.com/o/r", "repo_type": "github"}))
    cfg = config.load_global()
    assert cfg["remotes"] == {"default": {"type": "github", "url": "https://github.com/o/r"}}


def test_add_and_remove_remote(temp_config):
    config.add_remote("hf", "huggingface", "https://hf.co/o/r")
    assert config.get_remote("hf") == {"type": "huggingface", "url": "https://hf.co/o/r"}
    assert config.default_remote() == ("hf", {"type": "huggingface", "url": "https://hf.co/o/r"})
    assert config.remove_remote("hf") is True
    assert config.get_remote("hf") is None
    assert config.remove_remote("hf") is False


def test_default_remote_prefers_default_key(temp_config):
    config.add_remote("hf", "huggingface", "u1")
    config.add_remote("default", "github", "u2")
    name, cfg = config.default_remote()
    assert name == "default" and cfg["url"] == "u2"
