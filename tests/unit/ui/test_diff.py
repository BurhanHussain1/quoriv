"""Tests for `quoriv.ui.diff`."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from quoriv.ui.diff import compute_diff, render_edit_diff


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False, no_color=True)
    return console, buf


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_identical_strings_yield_empty_diff(self) -> None:
        assert compute_diff("same", "same") == ""

    def test_change_produces_unified_diff(self) -> None:
        diff = compute_diff("alpha\nbeta\n", "alpha\ngamma\n", file_path="/x.py")
        assert "---" in diff
        assert "+++" in diff
        assert "-beta" in diff
        assert "+gamma" in diff

    def test_includes_file_path_in_headers(self) -> None:
        diff = compute_diff("a", "b", file_path="/src/foo.py")
        assert "/src/foo.py" in diff

    def test_context_lines_respected(self) -> None:
        old = "line1\nline2\nline3\nTARGET\nline5\nline6\nline7\n"
        new = "line1\nline2\nline3\nCHANGED\nline5\nline6\nline7\n"
        # n=1 should include only 1 context line on each side
        diff = compute_diff(old, new, context_lines=1)
        assert "line3" in diff
        assert "line5" in diff
        assert "line1" not in diff  # too far

    def test_addition_only(self) -> None:
        diff = compute_diff("", "new content\n")
        assert "+new content" in diff

    def test_removal_only(self) -> None:
        diff = compute_diff("removed\n", "")
        assert "-removed" in diff


# ---------------------------------------------------------------------------
# render_edit_diff
# ---------------------------------------------------------------------------


class TestRenderEditDiff:
    def test_no_changes_renders_no_changes_line(self) -> None:
        console, buf = _make_console()
        render_edit_diff(
            console,
            file_path="/foo.py",
            old_string="same",
            new_string="same",
        )
        out = buf.getvalue()
        assert "no changes" in out
        assert "/foo.py" in out

    def test_change_renders_diff_block(self) -> None:
        console, buf = _make_console()
        render_edit_diff(
            console,
            file_path="/foo.py",
            old_string="alpha\n",
            new_string="beta\n",
        )
        out = buf.getvalue()
        assert "/foo.py" in out
        assert "edit_file" in out
        # Rich Syntax output is line-by-line; the diff markers must appear
        assert "-alpha" in out
        assert "+beta" in out

    def test_empty_file_path_falls_back_to_unknown(self) -> None:
        console, buf = _make_console()
        render_edit_diff(
            console,
            file_path="",
            old_string="x",
            new_string="y",
        )
        out = buf.getvalue()
        assert "edit_file" in out
