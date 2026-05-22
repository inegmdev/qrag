import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require real sentence-transformers embeddings (slow)",
    )


@pytest.fixture
def isolated_raghub(tmp_path, monkeypatch):
    """Redirect raghub cache/config to tmp_path for full test isolation."""
    cache = tmp_path / ".raghub"
    cache.mkdir(parents=True, exist_ok=True)
    import raghub.config
    import raghub.cli
    monkeypatch.setattr(raghub.config, "CACHE_DIR", cache)
    monkeypatch.setattr(raghub.config, "GLOBAL_CONFIG", cache / "config.json")
    monkeypatch.setattr(raghub.cli, "CACHE_DIR", cache)
    return cache
