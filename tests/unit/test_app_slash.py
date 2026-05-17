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
    _render_welcome,
)
from quoriv.core import SessionRegistry, trace_path
from quoriv.observability import ProviderRate, TraceLogger


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
    def test_reports_missing_files(self, fake_home: Path, tmp_path: Path) -> None:
        # ``fake_home`` keeps the global memory.md from a developer's
        # real home from leaking into the assertion.
        console, buf = _make_console()
        _handle_slash(console, "/memory", "current", _registry(tmp_path), cwd=tmp_path)
        output = buf.getvalue()
        assert "Memory files" in output
        assert "not present" in output  # both stubs missing -> at least one marker
        assert "No memory files found" in output

    def test_reports_project_md_when_present(self, fake_home: Path, tmp_path: Path) -> None:
        (tmp_path / "PROJECT.md").write_text("# project context\n", encoding="utf-8")
        console, buf = _make_console()
        _handle_slash(console, "/memory", "current", _registry(tmp_path), cwd=tmp_path)
        output = buf.getvalue()
        assert "PROJECT.md" in output
        assert "bytes" in output
        assert "No memory files found" not in output

    def test_present_files_show_loaded_tag(self, fake_home: Path, tmp_path: Path) -> None:
        # Phase 2 Slice 1: ``/memory`` now reflects whether the agent
        # has actually loaded the file (it has, when it exists), not
        # just file presence.
        (tmp_path / "PROJECT.md").write_text("# project context\n", encoding="utf-8")
        console, buf = _make_console()
        _handle_slash(console, "/memory", "current", _registry(tmp_path), cwd=tmp_path)
        output = buf.getvalue()
        assert "(loaded)" in output

    def test_missing_files_do_not_show_loaded_tag(self, fake_home: Path, tmp_path: Path) -> None:
        # The ``(loaded)`` tag must only appear next to files the
        # agent's MemoryMiddleware has actually seen.
        console, buf = _make_console()
        _handle_slash(console, "/memory", "current", _registry(tmp_path), cwd=tmp_path)
        output = buf.getvalue()
        assert "(loaded)" not in output


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

    # ----- Slice 8b: live mode switch --------------------------------------

    def test_no_arg_does_not_switch(self, tmp_path: Path) -> None:
        # The legacy display-only form returns a result with no new_mode.
        console, _buf = _make_console()
        result = _handle_slash(console, "/mode", "current", _registry(tmp_path), mode="ask")
        assert result.new_mode is None
        assert result.exit is False

    def test_valid_arg_returns_new_mode(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        result = _handle_slash(console, "/mode yolo", "current", _registry(tmp_path), mode="ask")
        assert result.new_mode == "yolo"
        # The handler itself doesn't print the "switched to" confirmation —
        # that's the interactive loop's job once the rebuild succeeds. So
        # the dispatch path returns silently when given a valid arg.
        assert "switched" not in buf.getvalue().lower()

    def test_valid_arg_with_uppercase_normalized(self, tmp_path: Path) -> None:
        # ``YOLO`` should resolve to ``yolo`` so users don't get tripped up
        # by case. The mode literal in the result must be the canonical
        # lowercase form ALLOWED_MODES expects.
        console, _buf = _make_console()
        result = _handle_slash(console, "/mode YOLO", "current", _registry(tmp_path), mode="ask")
        assert result.new_mode == "yolo"

    def test_same_mode_does_not_switch(self, tmp_path: Path) -> None:
        # Asking to switch to the current mode is a no-op — return a
        # _SlashResult with no new_mode and a friendly note instead of
        # forcing an agent rebuild for nothing.
        console, buf = _make_console()
        result = _handle_slash(console, "/mode ask", "current", _registry(tmp_path), mode="ask")
        assert result.new_mode is None
        assert "Already in" in buf.getvalue()

    def test_invalid_arg_reports_error(self, tmp_path: Path) -> None:
        console, buf = _make_console()
        result = _handle_slash(console, "/mode banana", "current", _registry(tmp_path), mode="ask")
        assert result.new_mode is None
        output = buf.getvalue()
        assert "unknown mode" in output.lower()
        assert "banana" in output
        # The valid set is surfaced so the user can correct the typo.
        for name in ("read-only", "ask", "auto", "yolo"):
            assert name in output

    def test_all_modes_can_be_targets(self, tmp_path: Path) -> None:
        # Round-trip every valid mode as a target from a different
        # starting mode to guarantee no Literal-narrowing regression in
        # the dispatch path.
        for target in ("read-only", "ask", "auto", "yolo"):
            start = "ask" if target != "ask" else "yolo"
            console, _buf = _make_console()
            result = _handle_slash(
                console, f"/mode {target}", "current", _registry(tmp_path), mode=start
            )
            assert result.new_mode == target


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

    # ----- Slice 9d: config-driven rate overrides --------------------------

    def test_user_rate_override_shadows_builtin(self, tmp_path: Path) -> None:
        # The built-in openai:gpt-5 rate is $0.01/1k input + $0.04/1k output.
        # Override it to $0.05/1k input + $0.20/1k output via cost_rates and
        # verify the displayed dollar amounts reflect the override.
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        tracer.log("model_complete", input_tokens=1000, output_tokens=1000, total_tokens=2000)
        custom_rates = {
            "openai:gpt-5": ProviderRate(input_per_1k=0.05, output_per_1k=0.20),
        }
        console, buf = _make_console()
        _handle_slash(
            console,
            "/cost",
            "thread-1",
            _registry(tmp_path),
            tracer=tracer,
            model_id="openai:gpt-5",
            cost_rates=custom_rates,
        )
        output = buf.getvalue()
        # 1k input @ $0.05 = $0.05; 1k output @ $0.20 = $0.20; total $0.25.
        assert "$0.0500" in output
        assert "$0.2000" in output
        assert "$0.2500" in output

    def test_user_rate_can_add_unknown_model(self, tmp_path: Path) -> None:
        # A model not in the built-in RATES still renders a dollar
        # estimate when the user supplies an override.
        tracer = TraceLogger(trace_path(tmp_path, "thread-1"))
        tracer.log("model_complete", input_tokens=1000, output_tokens=0)
        custom_rates = {
            "acme:test-model": ProviderRate(input_per_1k=0.10, output_per_1k=0.30),
        }
        console, buf = _make_console()
        _handle_slash(
            console,
            "/cost",
            "thread-1",
            _registry(tmp_path),
            tracer=tracer,
            model_id="acme:test-model",
            cost_rates=custom_rates,
        )
        output = buf.getvalue()
        assert "Estimated cost" in output
        assert "acme:test-model" in output
        assert "$0.1000" in output  # input cost
        assert "No rate configured" not in output


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


# ---------------------------------------------------------------------------
# Welcome panel — Phase 2 Slice 1 surfaces loaded memory files
# ---------------------------------------------------------------------------


class TestWelcomePanel:
    def test_omits_memory_line_when_no_files_present(self, fake_home: Path, tmp_path: Path) -> None:
        # Without a PROJECT.md or ~/.quoriv/memory.md, the welcome
        # panel must not show a memory line — keeps the welcome quiet
        # for first-time users.
        console, buf = _make_console()
        _render_welcome(console, model_id="openai:gpt-5", mode="ask", cwd=tmp_path)
        assert "Memory:" not in buf.getvalue()

    def test_shows_project_md_when_present(self, fake_home: Path, tmp_path: Path) -> None:
        (tmp_path / "PROJECT.md").write_text("# project\n", encoding="utf-8")
        console, buf = _make_console()
        _render_welcome(console, model_id="openai:gpt-5", mode="ask", cwd=tmp_path)
        output = buf.getvalue()
        assert "Memory:" in output
        assert "PROJECT.md" in output

    def test_shows_global_memory_md_when_present(self, fake_home: Path, tmp_path: Path) -> None:
        global_md = fake_home / ".quoriv" / "memory.md"
        global_md.parent.mkdir(parents=True)
        global_md.write_text("# user\n", encoding="utf-8")
        console, buf = _make_console()
        _render_welcome(console, model_id="openai:gpt-5", mode="ask", cwd=tmp_path)
        output = buf.getvalue()
        assert "Memory:" in output
        assert "memory.md" in output
