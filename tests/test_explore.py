"""Tests for explore.py — local version discovery, stats, and formatting.

Builds minimal real SQLite databases (plain relational tables only — no
sqlite-vec) under a temp CACHE_DIR, so the data layer is exercised end-to-end
without any network or embedding model.
"""
import datetime
import sqlite3

import pytest

from qrag import explore


def _make_code_db(path, languages, symbols):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE code_chunks (
            id INTEGER PRIMARY KEY, symbol_name TEXT, file_path TEXT, file_name TEXT,
            line_start INT, line_end INT, code_text TEXT, type TEXT, language TEXT,
            parent_name TEXT, call_depth INT, chunk_index INT
        );
        CREATE TABLE symbols (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, type TEXT, language TEXT,
            file_path TEXT, line_number INT, chunk_id INT
        );
        """
    )
    for lang in languages:
        conn.execute("INSERT INTO code_chunks (language, type) VALUES (?, 'function')", (lang,))
    for name, typ in symbols:
        conn.execute("INSERT INTO symbols (name, type) VALUES (?, ?)", (name, typ))
    conn.commit()
    conn.close()


def _make_docs_db(path, sections):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE doc_sections (
            id INTEGER PRIMARY KEY, source_path TEXT, doc_type TEXT, title TEXT,
            content TEXT, word_count INT
        );
        """
    )
    for source_path, words in sections:
        conn.execute(
            "INSERT INTO doc_sections (source_path, word_count) VALUES (?, ?)",
            (source_path, words),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(explore, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(explore, "load_global", lambda: {"active_versions": ["v1"]})

    v1 = tmp_path / "v1"
    v1.mkdir()
    _make_code_db(v1 / "code.db", ["c", "c", "cpp"],
                  [("GPIO_Init", "function"), ("gpio_t", "struct")])
    _make_docs_db(v1 / "docs.db",
                  [("gpio.pdf", 100), ("gpio.pdf", 50), ("uart.pdf", 30)])
    (v1 / "config.json").write_text('{"embedding_model": "all-MiniLM-L6-v2"}')

    v2 = tmp_path / "v2"
    v2.mkdir()
    _make_code_db(v2 / "code.db", ["python"], [("main", "function")])

    # noise that must not be picked up as versions
    (tmp_path / "logs").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "config.json").write_text("{}")
    return tmp_path


class TestDiscovery:
    def test_lists_only_version_dirs(self, cache):
        assert explore.local_version_names() == ["v1", "v2"]

    def test_empty_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(explore, "CACHE_DIR", tmp_path)
        assert explore.local_version_names() == []


class TestGatherVersion:
    def test_v1_full(self, cache):
        v = explore.gather_version("v1")
        assert v.has_code and v.has_docs
        assert v.active is True
        assert v.symbols == 2
        assert v.sections == 3
        assert v.docs == 2  # distinct source_path
        assert [(lc.language, lc.chunks) for lc in v.languages] == [("c", 2), ("cpp", 1)]
        assert v.size_bytes > 0
        assert isinstance(v.built_at, datetime.datetime)

    def test_v2_code_only_inactive(self, cache):
        v = explore.gather_version("v2")
        assert v.has_code and not v.has_docs
        assert v.active is False
        assert v.sections == 0 and v.docs == 0
        assert v.symbols == 1

    def test_gather_all(self, cache):
        assert [v.name for v in explore.gather_local_versions()] == ["v1", "v2"]


class TestComputeStats:
    def test_stats_v1(self, cache):
        s = explore.compute_stats("v1")
        assert s.code_chunks == 3
        assert s.symbols == 2
        assert s.words == 180
        assert dict(s.symbol_types) == {"function": 1, "struct": 1}
        assert s.embedding_model == "all-MiniLM-L6-v2"
        assert s.active is True

    def test_unknown_version_raises(self, cache):
        with pytest.raises(FileNotFoundError):
            explore.compute_stats("nope")


class TestDeleteLocal:
    def test_deletes_dir_and_deactivates(self, cache, monkeypatch):
        removed = {}
        monkeypatch.setattr(explore, "CACHE_DIR", cache)
        # delete_local imports remove_active_version from config at call time
        from qrag import config
        monkeypatch.setattr(config, "remove_active_version",
                            lambda name: removed.setdefault(name, True) or True)
        assert (cache / "v1").exists()
        was_active = explore.delete_local("v1")
        assert not (cache / "v1").exists()
        assert was_active is True
        assert removed == {"v1": True}

    def test_delete_missing_dir_is_safe(self, cache, monkeypatch):
        monkeypatch.setattr(explore, "CACHE_DIR", cache)
        from qrag import config
        monkeypatch.setattr(config, "remove_active_version", lambda name: False)
        # never-built version: no dir, not active → returns False, no error
        assert explore.delete_local("ghost") is False


class TestRemoveActiveVersion:
    def test_remove_active_version(self, tmp_path, monkeypatch):
        from qrag import config
        cfg_path = tmp_path / "config.json"
        monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(config, "GLOBAL_CONFIG", cfg_path)
        config.save_global({"active_versions": ["v1", "v2"]})
        assert config.remove_active_version("v1") is True
        assert config.load_global()["active_versions"] == ["v2"]
        assert config.remove_active_version("v1") is False


class TestFormatting:
    def test_lang_percentages(self):
        langs = [explore.LangCount("c", 2), explore.LangCount("cpp", 1)]
        pcts = dict(explore.lang_percentages(langs))
        assert round(pcts["c"]) == 67
        assert round(pcts["cpp"]) == 33

    def test_lang_percentages_empty(self):
        assert explore.lang_percentages([]) == []

    def test_human_size(self):
        assert explore.human_size(0) == "0 B"
        assert explore.human_size(512) == "512 B"
        assert explore.human_size(1536) == "1.5 KB"
        assert explore.human_size(5 * 1024 * 1024) == "5.0 MB"

    def test_human_age(self):
        now = datetime.datetime.now()
        assert explore.human_age(None) == "—"
        assert explore.human_age(now - datetime.timedelta(days=3)) == "3d ago"
        assert explore.human_age(now - datetime.timedelta(hours=2)) == "2h ago"
        assert explore.human_age(now - datetime.timedelta(minutes=5)) == "5m ago"
        assert explore.human_age(now - datetime.timedelta(seconds=10)) == "just now"
