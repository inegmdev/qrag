"""Tests for the TreeView widget and fuzzy_match (pure logic, no terminal).

The interactive browser loop needs a real TTY and readchar, so only the
navigation/selection/filter model is unit-tested here.
"""
from types import SimpleNamespace

from qrag.tui import (
    TreeNode,
    TreeView,
    build_file_tree,
    build_symbol_ast_tree,
    fuzzy_match,
)


def _sample() -> list[TreeNode]:
    return [
        TreeNode("stm32-v1", "stm32-v1", children=[
            TreeNode("size 84 MB", "stm32-v1:size"),
            TreeNode("languages: c cpp", "stm32-v1:langs"),
        ]),
        TreeNode("nrf52-v2", "nrf52-v2", children=[
            TreeNode("size 20 MB", "nrf52-v2:size"),
        ]),
        TreeNode("esp32-v3", "esp32-v3"),  # leaf, no children
    ]


class TestFuzzyMatch:
    def test_subsequence(self):
        assert fuzzy_match("stm", "stm32-v1")
        assert fuzzy_match("s31", "stm32-v1")   # subsequence, not substring
        assert fuzzy_match("", "anything")
        assert not fuzzy_match("xyz", "stm32-v1")

    def test_case_insensitive(self):
        assert fuzzy_match("STM", "stm32-v1")


class TestVisibility:
    def test_collapsed_shows_roots_only(self):
        tv = TreeView(_sample())
        assert [n.key for n, _ in tv.visible()] == ["stm32-v1", "nrf52-v2", "esp32-v3"]

    def test_toggle_expands_children(self):
        tv = TreeView(_sample())
        tv.toggle()  # expand stm32-v1 (index 0)
        keys = [n.key for n, _ in tv.visible()]
        assert keys == ["stm32-v1", "stm32-v1:size", "stm32-v1:langs", "nrf52-v2", "esp32-v3"]

    def test_toggle_on_leaf_is_noop(self):
        tv = TreeView(_sample())
        tv.index = 2  # esp32-v3, a leaf
        tv.toggle()
        assert len(tv.visible()) == 3

    def test_depths(self):
        tv = TreeView(_sample())
        tv.toggle()
        depths = {n.key: d for n, d in tv.visible()}
        assert depths["stm32-v1"] == 0
        assert depths["stm32-v1:size"] == 1


class TestNavigation:
    def test_move_clamps(self):
        tv = TreeView(_sample())
        tv.move(-5)
        assert tv.index == 0
        tv.move(100)
        assert tv.index == 2  # 3 visible roots
        assert tv.current.key == "esp32-v3"

    def test_current_tracks_selection(self):
        tv = TreeView(_sample())
        tv.move(1)
        assert tv.current.key == "nrf52-v2"


class TestFilter:
    def test_filter_matches_and_autoexpands(self):
        tv = TreeView(_sample())
        tv.set_filter("nrf")
        keys = [n.key for n, _ in tv.visible()]
        assert keys == ["nrf52-v2"]

    def test_filter_matches_child_keeps_ancestor(self):
        tv = TreeView(_sample())
        tv.set_filter("cpp")  # only matches stm32-v1's languages child
        keys = [n.key for n, _ in tv.visible()]
        assert keys[0] == "stm32-v1"
        assert "stm32-v1:langs" in keys
        assert "nrf52-v2" not in keys

    def test_filter_resets_index(self):
        tv = TreeView(_sample())
        tv.move(2)
        tv.set_filter("stm")
        assert tv.index == 0

    def test_empty_filter_restores_all(self):
        tv = TreeView(_sample())
        tv.set_filter("nrf")
        tv.set_filter("")
        assert len(tv.visible()) == 3


class TestRender:
    def test_render_empty(self):
        tv = TreeView([])
        # Should not raise and returns a renderable
        assert tv.render(empty_hint="none") is not None

    def test_render_nonempty(self):
        tv = TreeView(_sample())
        assert tv.render() is not None


class TestDiffTreeBuilders:
    def test_build_file_tree_folders(self):
        delta = SimpleNamespace(
            added=["drivers/gpio.c"], removed=["legacy/old.c"], changed=["drivers/uart.c"])
        roots = build_file_tree(delta)
        branches = {n.label: n for n in roots}
        assert "drivers/" in branches and "legacy/" in branches
        drivers_files = {c.label for c in branches["drivers/"].children}
        assert drivers_files == {"+ gpio.c", "~ uart.c"}
        assert {c.label for c in branches["legacy/"].children} == {"- old.c"}

    def test_build_file_tree_empty(self):
        delta = SimpleNamespace(added=[], removed=[], changed=[])
        roots = build_file_tree(delta)
        assert len(roots) == 1 and "no changes" in roots[0].label

    def test_build_symbol_ast_tree_nesting(self):
        def sc(name, parent, change):
            return SimpleNamespace(name=name, type="function", file_path="f.c",
                                   parent_name=parent, change=change)

        added = [sc("child", "parent", "added"), sc("parent", "", "added")]
        roots = build_symbol_ast_tree(added, [])
        assert len(roots) == 1
        parent = roots[0]
        assert parent.label == "+ parent (function)"
        assert [c.label for c in parent.children] == ["+ child (function)"]

    def test_build_symbol_ast_tree_empty(self):
        roots = build_symbol_ast_tree([], [])
        assert len(roots) == 1 and "no symbol changes" in roots[0].label


class TestBrowserAction:
    def test_activate_toggle(self, tmp_path, monkeypatch):
        import sqlite3

        from rich.console import Console

        from qrag import config, explore, tui

        v = tmp_path / "v1"
        v.mkdir()
        c = sqlite3.connect(v / "code.db")
        c.executescript(
            "CREATE TABLE code_chunks(id INTEGER PRIMARY KEY, language TEXT, type TEXT);"
            "CREATE TABLE symbols(id INTEGER PRIMARY KEY, name TEXT, type TEXT);")
        c.commit()
        c.close()

        cfg = tmp_path / "config.json"
        monkeypatch.setattr(explore, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(config, "GLOBAL_CONFIG", cfg)
        console = Console()

        msg1 = tui._browser_action("a", "v1", console)
        assert "activated" in msg1
        assert "v1" in config.load_global()["active_versions"]

        msg2 = tui._browser_action("a", "v1", console)
        assert "deactivated" in msg2
        assert "v1" not in config.load_global()["active_versions"]
