"""Tests for tui.py — fmt_eta, fmt_path, and BuildLayout layout constants."""
import pytest

from qrag.tui import MIN_HEIGHT, MIN_WIDTH, fmt_eta, fmt_path


class TestFmtEta:
    def test_zero_seconds(self):
        assert fmt_eta(0) == "0s"

    def test_under_one_minute(self):
        assert fmt_eta(30) == "30s"
        assert fmt_eta(59) == "59s"

    def test_exactly_one_minute(self):
        assert fmt_eta(60) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert fmt_eta(90) == "1m 30s"
        assert fmt_eta(3599) == "59m 59s"

    def test_exactly_one_hour(self):
        assert fmt_eta(3600) == "1h 0m"

    def test_hours_and_minutes(self):
        assert fmt_eta(3661) == "1h 1m"
        assert fmt_eta(7200) == "2h 0m"
        assert fmt_eta(7320) == "2h 2m"

    def test_float_truncated_to_int(self):
        assert fmt_eta(59.9) == "59s"
        assert fmt_eta(60.9) == "1m 0s"

    def test_large_value(self):
        result = fmt_eta(86400)  # 24 hours
        assert result == "24h 0m"


class TestFmtPath:
    def test_short_path_returned_as_relative(self):
        result = fmt_path("/root/a/b/file.c", "/root", 40)
        assert result == "a/b/file.c"

    def test_single_component_path(self):
        result = fmt_path("/root/file.c", "/root", 40)
        assert result == "file.c"

    def test_long_path_uses_ellipsis(self):
        result = fmt_path("/root/very/long/path/to/some/file.c", "/root", 20)
        assert "…" in result
        assert "file.c" in result

    def test_filename_always_preserved(self):
        result = fmt_path("/root/a/b/c/d/e/f/g/important.h", "/root", 20)
        assert "important.h" in result

    def test_max_width_respected(self):
        result = fmt_path("/root/very/long/nested/path/to/some/deep/file.c", "/root", 25)
        assert len(result) <= 25

    def test_invalid_root_falls_back_gracefully(self):
        result = fmt_path("/other/path/file.c", "/root", 40)
        assert "file.c" in result

    def test_exactly_fitting_path_no_ellipsis(self):
        # "a/b/file.c" is 10 chars, max_width=10 → no ellipsis
        result = fmt_path("/root/a/b/file.c", "/root", 10)
        assert result == "a/b/file.c"

    def test_start_preserved_in_ellipsis_form(self):
        # Should preserve the start of the path before the ellipsis
        result = fmt_path("/root/sdk/drivers/gpio/src/gpio.c", "/root", 30)
        # Result should be shorter than max_width and contain filename
        assert len(result) <= 30
        assert "gpio.c" in result

    def test_two_part_deep_path(self):
        # parent/filename when three-part ellipsis doesn't fit
        result = fmt_path("/root/verylongdirectoryname/subdir/file.c", "/root", 15)
        assert "file.c" in result


class TestBuildLayoutConstants:
    def test_min_height_is_positive(self):
        assert MIN_HEIGHT > 0

    def test_min_width_is_positive(self):
        assert MIN_WIDTH > 0

    def test_min_height_reasonable(self):
        # Must be large enough to show bars + panel
        assert MIN_HEIGHT >= 10

    def test_min_width_reasonable(self):
        assert MIN_WIDTH >= 40
