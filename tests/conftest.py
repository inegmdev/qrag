import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require real sentence-transformers embeddings (slow)",
    )


@pytest.fixture
def isolated_qrag(tmp_path, monkeypatch):
    """Redirect qrag cache/config to tmp_path for full test isolation."""
    cache = tmp_path / ".qrag"
    cache.mkdir(parents=True, exist_ok=True)
    import qrag.config
    import qrag.cli
    monkeypatch.setattr(qrag.config, "CACHE_DIR", cache)
    monkeypatch.setattr(qrag.config, "GLOBAL_CONFIG", cache / "config.json")
    monkeypatch.setattr(qrag.cli, "CACHE_DIR", cache)
    return cache
