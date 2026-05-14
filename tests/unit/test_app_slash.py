"""Tests for the slash-command dispatch in `quoriv.app`.

Focuses on the new Slice 7 commands (``/save`` / ``/load`` / ``/resume``)
plus the existing ``/exit`` / ``/clear`` / ``/help`` paths after the
signature change. Driving the full async chat loop is out of scope —
those slash handlers are pure functions over a real
:class:`SessionRegistry` and a Rich console.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

from quoriv.app import (
    SLASH_COMMANDS,
    _handle_slash,
)
from quoriv.core import SessionRegistry


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False, no_color=True)
    return console, buf


def _registry(tmp_path: Path) -> SessionRegistry:
    return SessionRegistry.for_cwd(tmp_path)


# ---------------------------------------------------------------------------
# SLASH_COMMANDS table
# ---------------------------------------------------------------------------


class TestSlashCommandsTable:
    def test_new_commands_listed(self) -> None:
        for cmd in ("/save", "/load", "/resume"):
            assert cmd in SLASH_COMMANDS

    def test_legacy_commands_still_listed(self) -> None:
        for cmd in ("/help", "/clear", "/exit", "/quit"):
            assert cmd in SLASH_COMMANDS


# ---------------------------------------------------------------------------
# /save
# ---------------------------------------------------------------------------


class TestSaveCommand:
    def test_save_with_name_persists(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        registry = _registry(tmp_path)
        result = _handle_slash(console, "/save feature-x", "abcdef0123", registry)
        assert result.exit is False
        assert result.new_thread_id is None
        record = registry.load("feature-x")
        assert record is not None
        assert record.thread_id == "abcdef0123"

    def test_save_defaults_to_thread_id_prefix(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        registry = _registry(tmp_path)
        _handle_slash(console, "/save", "abcdef0123456789", registry)
        record = registry.load("abcdef01")
        assert record is not None
        assert record.thread_id == "abcdef0123456789"

    def test_save_reports_success(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        registry = _registry(tmp_path)
        _handle_slash(console, "/save myname", "tid-1234", registry)
        output = buf.getvalue()
        assert "Saved" in output
        assert "myname" in output

    def test_save_empty_thread_id_reports_error(self, tmp_path: Path) -> None:
        # An empty thread_id with no name → derived name is also empty → ValueError.
        console, buf = _make_console()
        registry = _registry(tmp_path)
        result = _handle_slash(console, "/save", "", registry)
        assert result.new_thread_id is None
        assert registry.list_named() == []
        assert "/save" in buf.getvalue()

    def test_save_overwrites_previous(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        registry = _registry(tmp_path)
        _handle_slash(console, "/save x", "tid-1", registry)
        _handle_slash(console, "/save x", "tid-2", registry)
        record = registry.load("x")
        assert record is not None
        assert record.thread_id == "tid-2"


# ---------------------------------------------------------------------------
# /load
# ---------------------------------------------------------------------------


class TestLoadCommand:
    def test_load_known_switches_thread(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        registry = _registry(tmp_path)
        registry.save("feature-x", "tid-abc")
        result = _handle_slash(console, "/load feature-x", "current-tid", registry)
        assert result.new_thread_id == "tid-abc"

    def test_load_unknown_does_not_switch(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        registry = _registry(tmp_path)
        result = _handle_slash(console, "/load missing", "current", registry)
        assert result.new_thread_id is None
        assert "no saved session" in buf.getvalue()

    def test_load_without_arg_lists_when_empty(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        registry = _registry(tmp_path)
        result = _handle_slash(console, "/load", "current", registry)
        assert result.new_thread_id is None
        assert "No saved sessions" in buf.getvalue()

    def test_load_without_arg_lists_existing(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        registry = _registry(tmp_path)
        registry.save("alpha", "t-a")
        registry.save("beta", "t-b")
        _handle_slash(console, "/load", "current", registry)
        output = buf.getvalue()
        assert "alpha" in output
        assert "beta" in output


# ---------------------------------------------------------------------------
# /resume
# ---------------------------------------------------------------------------


class TestResumeCommand:
    def test_resume_switches_to_most_recent(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        registry = _registry(tmp_path)
        registry.save("a", "t-a", now=datetime(2026, 1, 1, tzinfo=UTC))
        registry.save("b", "t-b", now=datetime(2026, 1, 5, tzinfo=UTC))
        registry.save("c", "t-c", now=datetime(2026, 1, 3, tzinfo=UTC))
        result = _handle_slash(console, "/resume", "current", registry)
        assert result.new_thread_id == "t-b"

    def test_resume_with_empty_registry(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        registry = _registry(tmp_path)
        result = _handle_slash(console, "/resume", "current", registry)
        assert result.new_thread_id is None
        assert "no saved sessions" in buf.getvalue().lower()


# ---------------------------------------------------------------------------
# Legacy commands still work after the signature change
# ---------------------------------------------------------------------------


class TestLegacyCommands:
    def test_exit(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        result = _handle_slash(console, "/exit", "current", _registry(tmp_path))
        assert result.exit is True

    def test_quit(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        result = _handle_slash(console, "/quit", "current", _registry(tmp_path))
        assert result.exit is True

    def test_clear_rotates_thread(self, tmp_path: Path) -> None:
        console, _buf = _make_console()
        result = _handle_slash(console, "/clear", "current", _registry(tmp_path))
        assert result.exit is False
        assert result.new_thread_id is not None
        assert result.new_thread_id != "current"

    def test_help_lists_new_commands(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        _handle_slash(console, "/help", "current", _registry(tmp_path))
        output = buf.getvalue()
        for cmd in ("/save", "/load", "/resume", "/clear", "/exit"):
            assert cmd in output

    def test_unknown_command(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        result = _handle_slash(console, "/nope", "current", _registry(tmp_path))
        assert result.exit is False
        assert result.new_thread_id is None
        assert "Unknown command" in buf.getvalue()
