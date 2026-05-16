"""Tests for `quoriv.observability.trace`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from quoriv.core.persistence import trace_path
from quoriv.observability.trace import TraceLogger, _sanitize

# ---------------------------------------------------------------------------
# _sanitize — JSON coercion of arbitrary Python values
# ---------------------------------------------------------------------------


class TestSanitize:
    def test_passes_through_primitives(self) -> None:
        for value in (None, True, 0, 1.5, "abc"):
            assert _sanitize(value) == value

    def test_recurses_into_dicts(self) -> None:
        result = _sanitize({"a": 1, "b": {"c": 2}})
        assert result == {"a": 1, "b": {"c": 2}}

    def test_coerces_path_to_string(self, tmp_path: Path) -> None:
        result = _sanitize({"path": tmp_path / "file.txt"})
        assert isinstance(result["path"], str)
        assert "file.txt" in result["path"]

    def test_handles_dataclasses(self) -> None:
        @dataclass
        class Record:
            name: str
            count: int

        result = _sanitize(Record(name="x", count=3))
        assert result == {"name": "x", "count": 3}

    def test_handles_sets_and_tuples(self) -> None:
        # Sets aren't ordered, so we check membership.
        result = _sanitize({1, 2, 3})
        assert isinstance(result, list)
        assert set(result) == {1, 2, 3}
        assert _sanitize((1, "x")) == [1, "x"]

    def test_falls_back_to_str_for_unknown(self) -> None:
        class Custom:
            def __str__(self) -> str:
                return "custom-str"

        assert _sanitize(Custom()) == "custom-str"

    def test_non_string_dict_keys_stringified(self) -> None:
        result = _sanitize({1: "a", (2, 3): "b"})
        assert result == {"1": "a", "(2, 3)": "b"}


# ---------------------------------------------------------------------------
# TraceLogger — file I/O
# ---------------------------------------------------------------------------


class TestTraceLoggerWrites:
    def test_path_property(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        tracer = TraceLogger(path)
        assert tracer.path == path

    def test_lazy_creation_no_file_until_first_log(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "x.jsonl"
        TraceLogger(path)
        assert not path.exists()

    def test_log_creates_file_and_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "x.jsonl"
        tracer = TraceLogger(path)
        tracer.log("turn_start", user_input="hello")
        assert path.is_file()

    def test_log_appends_one_json_line_per_call(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        tracer = TraceLogger(path)
        tracer.log("turn_start")
        tracer.log("turn_end")
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        events = [json.loads(line) for line in lines]
        assert [e["event"] for e in events] == ["turn_start", "turn_end"]

    def test_log_includes_timestamp(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("turn_start")
        line = tracer.path.read_text(encoding="utf-8").splitlines()[0]
        record = json.loads(line)
        # ISO-8601 UTC timestamp: "...T...+00:00"
        assert "T" in record["timestamp"]
        assert record["timestamp"].endswith("+00:00")

    def test_log_includes_supplied_fields(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("model_complete", input_tokens=10, output_tokens=20)
        record = json.loads(tracer.path.read_text(encoding="utf-8").splitlines()[0])
        assert record["input_tokens"] == 10
        assert record["output_tokens"] == 20

    def test_log_sanitizes_unserializable_values(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("tool_start", path=tmp_path / "foo.txt")
        # Should not raise; the path becomes a string.
        record = json.loads(tracer.path.read_text(encoding="utf-8").splitlines()[0])
        assert isinstance(record["path"], str)


# ---------------------------------------------------------------------------
# TraceLogger — file reads
# ---------------------------------------------------------------------------


class TestTraceLoggerReads:
    def test_read_events_empty_when_missing(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "missing.jsonl")
        assert tracer.read_events() == []

    def test_read_events_returns_written(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("turn_start", user_input="hi")
        tracer.log("turn_end")
        events = tracer.read_events()
        assert [e["event"] for e in events] == ["turn_start", "turn_end"]
        assert events[0]["user_input"] == "hi"

    def test_read_events_skips_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        path.write_text(
            '{"event": "ok"}\n'
            "not json at all\n"
            "\n"  # blank line
            '{"event": "also ok"}\n',
            encoding="utf-8",
        )
        events = TraceLogger(path).read_events()
        assert [e["event"] for e in events] == ["ok", "also ok"]

    def test_read_events_skips_non_dict_json(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        path.write_text(
            '[1, 2, 3]\n"a string"\n{"event": "ok"}\n',
            encoding="utf-8",
        )
        events = TraceLogger(path).read_events()
        assert [e["event"] for e in events] == ["ok"]


# ---------------------------------------------------------------------------
# TraceLogger.token_totals
# ---------------------------------------------------------------------------


class TestTokenTotals:
    def test_empty_log_returns_zeros(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        totals = tracer.token_totals()
        assert totals == {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "model_calls": 0,
        }

    def test_sums_across_model_complete_events(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("model_complete", input_tokens=10, output_tokens=20, total_tokens=30)
        tracer.log("model_complete", input_tokens=5, output_tokens=15, total_tokens=20)
        totals = tracer.token_totals()
        assert totals["input_tokens"] == 15
        assert totals["output_tokens"] == 35
        assert totals["total_tokens"] == 50
        assert totals["model_calls"] == 2

    def test_falls_back_to_input_plus_output_when_total_missing(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("model_complete", input_tokens=10, output_tokens=20)  # no total_tokens
        totals = tracer.token_totals()
        assert totals["total_tokens"] == 30

    def test_ignores_non_model_complete_events(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("turn_start", input_tokens=999)  # should be ignored
        tracer.log("model_complete", input_tokens=5, output_tokens=10)
        totals = tracer.token_totals()
        assert totals["input_tokens"] == 5
        assert totals["model_calls"] == 1

    def test_ignores_non_int_token_fields(self, tmp_path: Path) -> None:
        tracer = TraceLogger(tmp_path / "x.jsonl")
        tracer.log("model_complete", input_tokens="not an int", output_tokens=10)
        totals = tracer.token_totals()
        assert totals["input_tokens"] == 0
        assert totals["output_tokens"] == 10


# ---------------------------------------------------------------------------
# Integration with trace_path
# ---------------------------------------------------------------------------


class TestTracePathIntegration:
    def test_canonical_location(self, tmp_path: Path) -> None:
        path = trace_path(tmp_path, "abc12345")
        assert path == tmp_path / ".quoriv" / "traces" / "abc12345.jsonl"

    def test_round_trip(self, tmp_path: Path) -> None:
        path = trace_path(tmp_path, "thread-1")
        tracer = TraceLogger(path)
        tracer.log("turn_start", user_input="hello")
        # A fresh logger reads what the first one wrote.
        events = TraceLogger(path).read_events()
        assert len(events) == 1
        assert events[0]["event"] == "turn_start"
