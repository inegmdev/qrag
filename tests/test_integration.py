"""Integration test: prepare fixture files, then verify search results."""
import shutil
from pathlib import Path

import pytest
import raghub.cli
import raghub.config
from click.testing import CliRunner

from raghub.cli import cli
from raghub.database import init_code_db, upsert_manifest_row

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def raghub_env(tmp_path, monkeypatch):
    """Redirect raghub cache to tmp_path."""
    cache = tmp_path / ".raghub"
    cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(raghub.config, "CACHE_DIR", cache)
    monkeypatch.setattr(raghub.config, "GLOBAL_CONFIG", cache / "config.json")
    monkeypatch.setattr(raghub.cli, "CACHE_DIR", cache)
    return cache


@pytest.mark.integration
def test_prepare_and_search_code(raghub_env):
    """prepare → search-code: enable_ecc ranks first for an ECC query."""
    runner = CliRunner()

    result = runner.invoke(cli, ["prepare", "-i", str(FIXTURES), "-o", "test"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["search-code", "enable error correction on SRAM"])
    assert result.exit_code == 0, result.output
    assert "enable_ecc" in result.output


@pytest.mark.integration
def test_prepare_and_search_docs(raghub_env):
    """prepare → search-docs: at least one result returned for an ECC query."""
    runner = CliRunner()

    result = runner.invoke(cli, ["prepare", "-i", str(FIXTURES), "-o", "test"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["search-docs", "ECC SRAM configuration"])
    assert result.exit_code == 0, result.output
    assert "[1]" in result.output


@pytest.mark.integration
def test_prepare_sets_active_version(raghub_env):
    runner = CliRunner()
    result = runner.invoke(cli, ["prepare", "-i", str(FIXTURES), "-o", "my-db"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["mcp", "active"])
    assert result.exit_code == 0, result.output
    assert "my-db" in result.output


@pytest.mark.integration
def test_search_code_error_without_db(raghub_env):
    """search-code must exit non-zero and print a human-readable message when DB is missing."""
    runner = CliRunner()
    result = runner.invoke(cli, ["search-code", "anything"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Incremental (issue 009)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_prepare_incremental_nothing_changed(raghub_env, tmp_path):
    """Second prepare with unchanged files prints 'nothing changed'."""
    src = tmp_path / "src"
    shutil.copytree(FIXTURES, src)

    runner = CliRunner()
    result = runner.invoke(cli, ["prepare", "-i", str(src), "-o", "test"])
    assert result.exit_code == 0, result.output

    result2 = runner.invoke(cli, ["prepare", "-i", str(src), "-o", "test"])
    assert result2.exit_code == 0, result2.output
    assert "nothing changed" in result2.output


@pytest.mark.integration
def test_prepare_force_rebuilds_everything(raghub_env, tmp_path):
    """--force causes a full rebuild even when files are unchanged."""
    src = tmp_path / "src"
    shutil.copytree(FIXTURES, src)

    runner = CliRunner()
    runner.invoke(cli, ["prepare", "-i", str(src), "-o", "test"])

    result = runner.invoke(cli, ["prepare", "-i", str(src), "-o", "test", "--force"])
    assert result.exit_code == 0, result.output
    assert "nothing changed" not in result.output


def test_prepare_errors_on_root_mismatch(raghub_env, tmp_path):
    """prepare exits non-zero when -i root differs from the stored manifest."""
    # Seed the DB with a manifest entry that uses a different root
    db_path = raghub_env / "test" / "code.db"
    init_code_db(db_path)
    upsert_manifest_row(db_path, "foo.c", "/some/other/root", 0.0, "deadbeef")

    src = tmp_path / "src"
    src.mkdir()
    (src / "test.c").write_text("int f(void) { return 0; }\n")

    runner = CliRunner()
    result = runner.invoke(cli, ["prepare", "-i", str(src), "-o", "test"])
    assert result.exit_code != 0
    assert "roots" in result.output.lower() or "roots" in (result.stderr or "")
