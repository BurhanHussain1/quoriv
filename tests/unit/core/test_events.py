"""Tests for `quoriv.core.events`."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from quoriv.core.events import (
    _format_args,
    render_token,
    render_tool_end,
    render_tool_start,
)


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False, no_color=True)
    return console, buf


# ---------------------------------------------------------------------------
# render_token
# ---------------------------------------------------------------------------


class TestRenderToken:
    def test_writes_text_to_console(self) -> None:
        console, buf = _make_console()
        render_token(console, "hello ")
        render_token(console, "world")
        assert "hello world" in buf.getvalue()

    def test_empty_token_writes_nothing(self) -> None:
        console, buf = _make_console()
        render_token(console, "")
        assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# render_tool_start
# ---------------------------------------------------------------------------


class TestRenderToolStart:
    def test_includes_tool_name(self) -> None:
        console, buf = _make_console()
        render_tool_start(console, "read_file", {"file_path": "/foo.py"})
        out = buf.getvalue()
        assert "read_file" in out

    def test_includes_args(self) -> None:
        console, buf = _make_console()
        render_tool_start(console, "read_file", {"file_path": "/foo.py"})
        out = buf.getvalue()
        assert "file_path" in out
        assert "/foo.py" in out

    def test_non_dict_args_does_not_crash(self) -> None:
        console, buf = _make_console()
        render_tool_start(console, "weird_tool", "raw string arg")
        assert "weird_tool" in buf.getvalue()


# ---------------------------------------------------------------------------
# render_tool_end
# ---------------------------------------------------------------------------


class TestRenderToolEnd:
    def test_prints_short_output_verbatim(self) -> None:
        console, buf = _make_console()
        render_tool_end(console, "hello")
        assert "hello" in buf.getvalue()

    def test_truncates_long_output(self) -> None:
        console, buf = _make_console()
        render_tool_end(console, "x" * 1000, max_len=100)
        out = buf.getvalue()
        assert "truncated" in out

    def test_none_output_is_safe(self) -> None:
        console, buf = _make_console()
        render_tool_end(console, None)
        # Should produce at least an empty-line render without crashing.
        assert buf.getvalue() is not None

    def test_indents_multiline(self) -> None:
        console, buf = _make_console()
        render_tool_end(console, "line one\nline two")
        out = buf.getvalue()
        assert "line one" in out
        assert "line two" in out


# ---------------------------------------------------------------------------
# _format_args
# ---------------------------------------------------------------------------


class TestFormatArgs:
    def test_renders_key_equals_value(self) -> None:
        out = _format_args({"name": "x", "count": 5})
        assert "name='x'" in out
        assert "count=5" in out

    def test_truncates_long_individual_values(self) -> None:
        out = _format_args({"x": "a" * 200})
        assert "…" in out

    def test_truncates_overall_render(self) -> None:
        out = _format_args({f"k{i}": i for i in range(50)}, max_len=80)
        assert out.endswith("…")
        assert len(out) <= 81  # 80 chars + the ellipsis

    def test_non_dict_passes_through_repr(self) -> None:
        out = _format_args([1, 2, 3])
        assert isinstance(out, str)
        assert "[1, 2, 3]" in out

    def test_empty_dict(self) -> None:
        assert _format_args({}) == ""
