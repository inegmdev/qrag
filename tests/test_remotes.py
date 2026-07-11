"""Tests for the remote backend layer and remotes config.

Every test mocks the transport boundary (github_distribution / config), so no
network or `gh` CLI is touched.
"""
import datetime
import json
import types

import pytest

from qrag import config, explore


def _proc(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


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


# ---------------------------------------------------------------------------
# Backend registry: all four types present + resolvable
# ---------------------------------------------------------------------------

def test_all_backends_registered():
    assert set(explore.backend_types()) >= {"github", "huggingface", "jfrog", "gitlfs"}


def test_get_backend_huggingface(monkeypatch):
    monkeypatch.setattr(config, "get_remote",
                        lambda n: {"type": "huggingface", "url": "org/repo"})
    assert isinstance(explore.get_backend("hf"), explore.HFBackend)


def test_run_cli_missing_binary(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(explore.RemoteError, match="'jf' not found"):
        explore._run_cli(["jf", "rt", "ping"], "jf")


# ---------------------------------------------------------------------------
# HuggingFace backend (mocked SDK)
# ---------------------------------------------------------------------------

def test_hf_repo_id_parsing():
    for url in ("https://huggingface.co/datasets/org/repo", "org/repo", "hf://org/repo"):
        assert explore.HFBackend(url, "hf")._repo_id() == "org/repo"


def test_hf_check_auth_no_token(monkeypatch):
    b = explore.HFBackend("org/repo", "hf")
    monkeypatch.setattr(b, "_token", lambda: None)
    with pytest.raises(explore.RemoteError, match="No HuggingFace"):
        b.check_auth()


def test_hf_list_versions(monkeypatch):
    b = explore.HFBackend("org/repo", "hf")
    api = types.SimpleNamespace(
        list_repo_files=lambda repo_id, repo_type: [
            "v1/code.db", "v1/manifest.json", "v2/docs.db", "README.md",
        ])
    monkeypatch.setattr(b, "_api", lambda: api)
    assert [v.name for v in b.list_versions()] == ["v1", "v2"]


def test_hf_download_copies_only_version_files(tmp_path, monkeypatch):
    import huggingface_hub
    b = explore.HFBackend("org/repo", "hf")
    api = types.SimpleNamespace(
        list_repo_files=lambda repo_id, repo_type: ["v1/code.db", "v1/config.json", "v2/docs.db"])
    monkeypatch.setattr(b, "_api", lambda: api)
    monkeypatch.setattr(b, "_token", lambda: "tok")

    downloads = tmp_path / "hf"
    downloads.mkdir()

    def fake_dl(repo_id, path, repo_type=None, token=None):
        p = downloads / path.replace("/", "_")
        p.write_text("data")
        return str(p)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_dl)
    dest = tmp_path / "cache"
    dest.mkdir()
    b.download("v1", dest)
    assert (dest / "v1" / "code.db").exists()
    assert (dest / "v1" / "config.json").exists()
    assert not (dest / "v1" / "docs.db").exists()  # v2 excluded


# ---------------------------------------------------------------------------
# JFrog backend (mocked jf CLI)
# ---------------------------------------------------------------------------

def test_jfrog_list_versions(monkeypatch):
    b = explore.JFrogBackend("my-repo/qrag", "jf")
    hits = [{"path": "my-repo/qrag/v1/manifest.json"},
            {"path": "my-repo/qrag/v2/manifest.json"}]
    seen = {}

    def fake_run(cmd, binary):
        seen["cmd"] = cmd
        return _proc(stdout=json.dumps(hits))

    monkeypatch.setattr(explore, "_run_cli", fake_run)
    assert [v.name for v in b.list_versions()] == ["v1", "v2"]
    assert seen["cmd"][:3] == ["jf", "rt", "search"]


def test_jfrog_list_versions_error(monkeypatch):
    b = explore.JFrogBackend("my-repo/qrag", "jf")
    monkeypatch.setattr(explore, "_run_cli", lambda cmd, binary: _proc(returncode=1, stderr="boom"))
    with pytest.raises(explore.RemoteError, match="JFrog search failed"):
        b.list_versions()


# ---------------------------------------------------------------------------
# git+LFS backend (mocked clone / git)
# ---------------------------------------------------------------------------

def test_gitlfs_check_auth(monkeypatch):
    b = explore.GitLFSBackend("u", "git")
    monkeypatch.setattr(explore, "_run_cli", lambda cmd, binary: _proc(stdout="git version 2.x"))
    b.check_auth()  # no raise


def test_gitlfs_list_versions(monkeypatch):
    b = explore.GitLFSBackend("u", "git")

    def fake_clone(work):
        work.mkdir(parents=True)
        (work / ".git").mkdir()
        for v, db in (("v1", "code.db"), ("v2", "docs.db")):
            (work / v).mkdir()
            (work / v / db).write_text("x")
        (work / "notes").mkdir()  # no db → excluded
        (work / "notes" / "readme.txt").write_text("x")

    monkeypatch.setattr(b, "_clone", fake_clone)
    assert [v.name for v in b.list_versions()] == ["v1", "v2"]


def test_gitlfs_download_missing_version(monkeypatch):
    b = explore.GitLFSBackend("u", "git")
    monkeypatch.setattr(b, "_clone", lambda work: work.mkdir(parents=True))
    with pytest.raises(explore.RemoteError, match="not found in git remote"):
        b.download("v9", explore.CACHE_DIR)


# ---------------------------------------------------------------------------
# set_origin_remote
# ---------------------------------------------------------------------------

def test_set_origin_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(explore, "CACHE_DIR", tmp_path)
    (tmp_path / "v1").mkdir()
    (tmp_path / "v1" / "config.json").write_text(
        '{"origin_version": "v1", "embedding_model": "m"}')
    explore.set_origin_remote("v1", "hf")
    data = json.loads((tmp_path / "v1" / "config.json").read_text())
    assert data["origin_remote"] == "hf"
    assert data["origin_version"] == "v1"   # preserved
    assert data["embedding_model"] == "m"   # preserved


# ---------------------------------------------------------------------------
# push resolution (#45)
# ---------------------------------------------------------------------------

@explore.register_backend("readonly-test")
class _ReadOnlyBackend(explore.RemoteBackend):
    can_push = False

    def check_auth(self):
        ...

    def list_versions(self):
        return []

    def download(self, version, dest_dir):
        ...

    def push(self, version, src_dir, *, force=False):
        ...

    def delete_remote(self, version):
        ...


def test_get_origin_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(explore, "CACHE_DIR", tmp_path)
    (tmp_path / "v1").mkdir()
    (tmp_path / "v1" / "config.json").write_text('{"origin_remote": "hf"}')
    (tmp_path / "v2").mkdir()
    (tmp_path / "v2" / "config.json").write_text("{}")
    assert explore.get_origin_remote("v1") == "hf"
    assert explore.get_origin_remote("v2") is None
    assert explore.get_origin_remote("ghost") is None


def test_resolve_push_backend_explicit(monkeypatch):
    monkeypatch.setattr(config, "get_remote", lambda n: {"type": "github", "url": "u"})
    backend = explore.resolve_push_backend("v1", "origin")
    assert isinstance(backend, explore.GitHubBackend) and backend.name == "origin"


def test_resolve_push_backend_uses_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(explore, "CACHE_DIR", tmp_path)
    (tmp_path / "v1").mkdir()
    (tmp_path / "v1" / "config.json").write_text('{"origin_remote": "gh2"}')
    seen = {}

    def fake_get_remote(name):
        seen["name"] = name
        return {"type": "github", "url": "u"}

    monkeypatch.setattr(config, "get_remote", fake_get_remote)
    backend = explore.resolve_push_backend("v1", None)
    assert seen["name"] == "gh2"
    assert backend.name == "gh2"


def test_resolve_push_backend_readonly(monkeypatch):
    monkeypatch.setattr(config, "get_remote", lambda n: {"type": "readonly-test", "url": "u"})
    with pytest.raises(explore.RemoteError, match="read-only"):
        explore.resolve_push_backend("v1", "mirror")
