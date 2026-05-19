"""Tests for ``quoriv.replay`` — Phase 3 Slice 12."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from rich.console import Console

from quoriv.replay import _format_record, replay_thread


def _console() -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(file=buf, width=10_000, force_terminal=False, no_color=True), buf


class TestFormatRecord:
    def test_turn_start_contains_user_input(self) -> None:
        line = _format_record(
            {
                "event": "turn_start",
                "timestamp": "2026-05-19T10:30:00+00:00",
                "user_input": "fix the bug",
                "mode": "ask",
            }
        )
        assert "turn start" in line
        assert "fix the bug" in line
        assert "mode=ask" in line

    def test_model_complete_shows_token_counts(self) -> None:
        line = _format_record(
            {
                "event": "model_complete",
                "timestamp": "2026-05-19T10:30:01+00:00",
                "model": "openai:gpt-4.1",
                "input_tokens": 120,
                "output_tokens": 45,
            }
        )
        assert "openai:gpt-4.1" in line
        assert "in=120" in line
        assert "out=45" in line

    def test_tool_start_shows_name_and_args(self) -> None:
        line = _format_record(
            {
                "event": "tool_start",
                "timestamp": "2026-05-19T10:30:02+00:00",
                "tool_name": "read_file",
                "args": {"path": "src/main.py"},
            }
        )
        assert "read_file" in line
        assert "src/main.py" in line

    def test_tool_end_shows_preview(self) -> None:
        line = _format_record(
            {
                "event": "tool_end",
                "timestamp": "2026-05-19T10:30:03+00:00",
                "tool_name": "read_file",
                "output_preview": "file contents here",
            }
        )
        assert "read_file" in line
        assert "file contents here" in line

    def test_turn_end_minimal_render(self) -> None:
        line = _format_record({"event": "turn_end", "timestamp": "2026-05-19T10:30:04+00:00"})
        assert "turn end" in line

    def test_unknown_event_falls_back_to_json(self) -> None:
        line = _format_record({"event": "custom_thing", "data": "anything"})
        assert "custom_thing" in line


class TestReplayThread:
    def test_missing_file_prints_message_and_returns_zero(self, tmp_path: Path) -> None:
        console, buf = _console()
        path = tmp_path / "missing.jsonl"
        n = replay_thread(console, path)
        assert n == 0
        assert "No events" in buf.getvalue()

    def test_full_trace_renders_each_event(self, tmp_path: Path) -> None:
        events = [
            {"event": "turn_start", "user_input": "hi", "mode": "yolo"},
            {
                "event": "model_complete",
                "model": "openai:gpt-4o",
                "input_tokens": 10,
                "output_tokens": 5,
            },
            {"event": "tool_start", "tool_name": "ls", "args": {"path": "."}},
            {"event": "tool_end", "tool_name": "ls", "output_preview": "main.py\n"},
            {"event": "turn_end"},
        ]
        path = tmp_path / "thread.jsonl"
        path.write_text(
            "\n".join(json.dumps(e) for e in events) + "\n",
            encoding="utf-8",
        )
        console, buf = _console()
        n = replay_thread(console, path)
        assert n == 5
        out = buf.getvalue()
        # Every event left a fingerprint in the rendered output.
        assert "Replay" in out
        assert "5 events" in out
        assert "hi" in out  # turn_start payload
        assert "openai:gpt-4o" in out
        assert "ls" in out
        assert "main.py" in out

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "thread.jsonl"
        path.write_text(
            "\n".join(
                [
                    json.dumps({"event": "turn_start", "user_input": "first"}),
                    "not valid json {{{",
                    json.dumps({"event": "turn_end"}),
                ]
            ),
            encoding="utf-8",
        )
        console, buf = _console()
        n = replay_thread(console, path)
        # Two parseable lines; the garbage line is silently dropped
        # by ``TraceLogger.read_events``.
        assert n == 2
        out = buf.getvalue()
        assert "first" in out
        assert "turn end" in out
