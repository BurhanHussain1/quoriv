"""Tests for ``quoriv.ui.banner`` — Phase 5 Slice 1."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from quoriv import __version__
from quoriv.ui.banner import render_welcome_banner


def _capture() -> tuple[Console, StringIO]:
    """Build a Rich console that writes into an in-memory buffer.

    Width is wide enough that long ``tmp_path`` values don't get wrapped
    across visual lines — string-match assertions need contiguous text.
    """
    buf = StringIO()
    return Console(file=buf, width=10_000, force_terminal=False, no_color=True), buf


class TestRenderWelcomeBanner:
    def test_renders_without_crashing(self, tmp_path: Path) -> None:
        # Smoke check: every required arg supplied, no slash dict.
        console, buf = _capture()
        render_welcome_banner(console, model_id="openai:gpt-4o", mode="ask", cwd=tmp_path)
        assert buf.getvalue()  # Something printed.

    def test_includes_version_model_mode_cwd(self, tmp_path: Path) -> None:
        console, buf = _capture()
        render_welcome_banner(
            console,
            model_id="anthropic:claude-sonnet-4",
            mode="yolo",
            cwd=tmp_path,
        )
        out = buf.getvalue()
        assert __version__ in out
        assert "anthropic:claude-sonnet-4" in out
        assert "yolo" in out
        assert str(tmp_path) in out

    def test_omits_memory_row_when_empty(self, tmp_path: Path) -> None:
        # First-time users without a PROJECT.md should not see a stray
        # "Memory:" row pointing at nothing.
        console, buf = _capture()
        render_welcome_banner(
            console,
            model_id="openai:gpt-4o",
            mode="ask",
            cwd=tmp_path,
            memory_files=[],
        )
        assert "Memory" not in buf.getvalue()

    def test_includes_memory_filenames_when_supplied(self, tmp_path: Path) -> None:
        console, buf = _capture()
        memory = [tmp_path / "PROJECT.md", tmp_path / "memory.md"]
        render_welcome_banner(
            console,
            model_id="openai:gpt-4o",
            mode="ask",
            cwd=tmp_path,
            memory_files=memory,
        )
        out = buf.getvalue()
        assert "PROJECT.md" in out
        assert "memory.md" in out

    def test_renders_slash_command_grid(self, tmp_path: Path) -> None:
        console, buf = _capture()
        slash = {"/help": "show help", "/exit": "leave the chat"}
        render_welcome_banner(
            console,
            model_id="openai:gpt-4o",
            mode="ask",
            cwd=tmp_path,
            slash_commands=slash,
        )
        out = buf.getvalue()
        assert "/help" in out
        assert "show help" in out
        assert "/exit" in out
        assert "leave the chat" in out

    def test_help_hint_always_present(self, tmp_path: Path) -> None:
        # The /help and /exit hints are the safety net for users who
        # missed the slash grid (e.g. on a narrow terminal).
        console, buf = _capture()
        render_welcome_banner(console, model_id="openai:gpt-4o", mode="ask", cwd=tmp_path)
        out = buf.getvalue()
        assert "/help" in out
        assert "/exit" in out

    def test_none_cwd_does_not_crash(self) -> None:
        # `quoriv chat` without --cwd passes cwd=None down the call chain.
        console, buf = _capture()
        render_welcome_banner(console, model_id="openai:gpt-4o", mode="ask", cwd=None)
        assert "current directory" in buf.getvalue()
