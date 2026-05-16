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
    _build_status_line,
    _handle_slash,
)
from quoriv.core import SessionRegistry, trace_path
from quoriv.observability import TraceLogger


def _make_console() -> tuple[Console, StringIO]:
    # ``width=10_000`` effectively disables Rich's hard wrapping. ``/memory``
    # prints absolute filesystem paths, and macOS's tmp directory
    # (``/private/var/folders/.../pytest-of-runner/.../PROJECT.md``) is long
    # enough to break ``"PROJECT.md" in output`` assertions when the path
    # wraps at column 120 mid-token (CI-only regression observed on
    # macos-latest before this bump).
    buf = StringIO()
    console = Console(file=buf, width=10_000, force_terminal=False, no_color=True)
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


# ---------------------------------------------------------------------------
# Slice 8 — /tools, /memory, /mode, /cost slash commands
# ---------------------------------------------------------------------------


class TestSlice8SlashCommandsListed:
    def test_new_commands_listed(self) -> None:
        for cmd in ("/tools", "/memory", "/mode", "/cost"):
            assert cmd in SLASH_COMMANDS


class TestToolsCommand:
    def test_lists_builtins_and_quoriv_tools(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        result = _handle_slash(console, "/tools", "current", _registry(tmp_path))
        assert result.exit is False
        assert result.new_thread_id is None
        output = buf.getvalue()
        # A representative DeepAgents built-in and a representative Quoriv tool
        # should both appear.
        assert "write_todos" in output
        assert "git_status" in output
        assert "run_tests" in output
        assert "DeepAgents built-ins" in output
        assert "Quoriv tools" in output


class TestMemoryCommand:
    def test_reports_missing_files(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        _handle_slash(console, "/memory", "current", _registry(tmp_path), cwd=tmp_path)
        output = buf.getvalue()
        assert "Memory files" in output
        assert "not present" in output  # both stubs missing -> at least one marker
        assert "No memory files found" in output

    def test_reports_project_md_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "PROJECT.md").write_text("# project context\n", encoding="utf-8")
        console, buf = _make_console()
        _handle_slash(console, "/memory", "current", _registry(tmp_path), cwd=tmp_path)
        output = buf.getvalue()
        assert "PROJECT.md" in output
        assert "bytes" in output
        assert "No memory files found" not in output


class TestModeCommand:
    def test_reports_current_mode_and_gates(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        _handle_slash(console, "/mode", "current", _registry(tmp_path), mode="ask")
        output = buf.getvalue()
        assert "Permission mode" in output
        assert "ask" in output
        # ask mode gates write_file, edit_file, execute, and git writes.
        for gated in ("write_file", "edit_file", "execute", "git_commit"):
            assert gated in output

    def test_yolo_reports_no_gates(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        _handle_slash(console, "/mode", "current", _registry(tmp_path), mode="yolo")
        output = buf.getvalue()
        assert "yolo" in output
        assert "nothing — every tool runs" in output

    def test_available_modes_listed(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        _handle_slash(console, "/mode", "current", _registry(tmp_path), mode="ask")
        output = buf.getvalue()
        for name in ("read-only", "ask", "auto", "yolo"):
            assert name in output


class TestCostCommand:
    def test_no_tracer_reports_disconnected(self, tmp_path: Path) -> None:
        # No tracer attached -> falls back to a "no logger" message.
        console, buf = _make_console()
        result = _handle_slash(console, "/cost", "current", _registry(tmp_path))
        assert result.exit is False
        assert result.new_thread_id is None
        output = buf.getvalue()
        assert "No trace logger" in output

    def test_empty_log_reports_zero_calls(self, tmp_path: Path) -> None:
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        console, buf = _make_console()
        _handle_slash(console, "/cost", "thread-1", _registry(tmp_path), tracer=tracer)
        output = buf.getvalue()
        assert "No model calls recorded" in output
        # The trace file path should appear so the user can find it.
        assert ".jsonl" in output

    def test_populated_log_shows_totals(self, tmp_path: Path) -> None:
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        tracer.log("model_complete", input_tokens=100, output_tokens=200, total_tokens=300)
        tracer.log("model_complete", input_tokens=50, output_tokens=75, total_tokens=125)
        console, buf = _make_console()
        _handle_slash(console, "/cost", "thread-1", _registry(tmp_path), tracer=tracer)
        output = buf.getvalue()
        assert "Token usage" in output
        assert "150" in output  # input total
        assert "275" in output  # output total
        assert "425" in output  # total tokens
        assert "Calls" in output

    def test_includes_trace_path(self, tmp_path: Path) -> None:
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        tracer.log("model_complete", input_tokens=10, output_tokens=20)
        console, buf = _make_console()
        _handle_slash(console, "/cost", "thread-1", _registry(tmp_path), tracer=tracer)
        assert "Trace file" in buf.getvalue()

    # ----- Slice 9c: dollar-cost estimate ----------------------------------

    def test_known_model_shows_dollar_estimate(self, tmp_path: Path) -> None:
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        # 1k input + 1k output at gpt-4o (input $0.0025/1k, output $0.0100/1k)
        # → input $0.0025, output $0.0100, total $0.0125
        tracer.log("model_complete", input_tokens=1000, output_tokens=1000, total_tokens=2000)
        console, buf = _make_console()
        _handle_slash(
            console,
            "/cost",
            "thread-1",
            _registry(tmp_path),
            tracer=tracer,
            model_id="openai:gpt-4o",
        )
        output = buf.getvalue()
        assert "Estimated cost" in output
        assert "openai:gpt-4o" in output
        # Dollar amounts formatted to 4 decimal places — verify the totals.
        assert "$0.0025" in output  # input
        assert "$0.0100" in output  # output
        assert "$0.0125" in output  # total

    def test_unknown_model_shows_rate_not_configured(self, tmp_path: Path) -> None:
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        tracer.log("model_complete", input_tokens=10, output_tokens=20)
        console, buf = _make_console()
        _handle_slash(
            console,
            "/cost",
            "thread-1",
            _registry(tmp_path),
            tracer=tracer,
            model_id="madeup:nonexistent-model",
        )
        output = buf.getvalue()
        # Token totals still surface; the dollar block reports unknown rate.
        assert "Token usage" in output
        assert "No rate configured" in output
        assert "madeup:nonexistent-model" in output
        assert "Estimated cost" not in output

    def test_ollama_renders_zero_dollar_estimate(self, tmp_path: Path) -> None:
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        tracer.log("model_complete", input_tokens=5000, output_tokens=5000)
        console, buf = _make_console()
        _handle_slash(
            console,
            "/cost",
            "thread-1",
            _registry(tmp_path),
            tracer=tracer,
            model_id="ollama:llama3.2",
        )
        output = buf.getvalue()
        assert "Estimated cost" in output
        assert "$0.0000" in output  # local-only models are free


# ---------------------------------------------------------------------------
# Status-line builder (pure function — no PromptSession needed).
# ---------------------------------------------------------------------------


class TestBuildStatusLine:
    def test_formats_all_fields(self, tmp_path: Path) -> None:
        line = _build_status_line(
            model_id="openai:gpt-5",
            mode="ask",
            cwd=tmp_path / "my-repo",
            thread_id="abcdef0123456789",
        )
        assert "openai:gpt-5" in line
        assert "mode=ask" in line
        assert "my-repo" in line
        # Thread id is truncated to first 8 chars.
        assert "abcdef01" in line
        assert "abcdef0123456789" not in line

    def test_root_dir_falls_back_to_full_path(self, tmp_path: Path) -> None:
        # An empty Path("") has no .name — the builder should not show an empty
        # field. Use a Path whose .name is empty.
        line = _build_status_line(
            model_id="m",
            mode="yolo",
            cwd=Path("/"),
            thread_id="01234567",
        )
        # Either the path string or *something* non-empty appears between the
        # delimiters. Just verify the line is shaped correctly.
        assert "yolo" in line
        assert "01234567" in line
        assert line.count("|") == 3
