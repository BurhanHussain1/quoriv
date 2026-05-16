"""Local JSONL trace log — Phase 1 Slice 9.

One JSON object per line, append-only, keyed by ``thread_id``. The
chat loop opens a :class:`TraceLogger` per thread and records:

    turn_start         user_input
    model_complete     {input_tokens, output_tokens, total_tokens, model}
    tool_start         tool_name, args
    tool_end           tool_name, output_preview
    turn_end           exit_kind

Records are written with :func:`json.dumps` after a small recursive
sanitization pass so unserializable values (e.g.,
:class:`pathlib.Path`, dataclasses, langgraph types) become strings
instead of raising.

The on-disk shape is intentionally flat JSONL so an agent can read the
file with ``read_file`` + parsing without needing a database driver,
and so external tooling (``jq``, ``head``, ``tail``) just works.

The companion path helper :func:`quoriv.core.persistence.trace_path`
returns the canonical filesystem location:
``<cwd>/.quoriv/traces/<thread_id>.jsonl``.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def _sanitize(value: Any) -> Any:
    """Coerce arbitrary values into JSON-friendly form.

    Recursively walks dicts and lists. Dataclass instances are flattened
    to dicts. Anything else that isn't already JSON-native is converted
    via :func:`str`.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _sanitize(dataclasses.asdict(value))
    return str(value)


class TraceLogger:
    """Append-only JSONL writer for one chat thread.

    The file is created lazily on first :meth:`log` so an unused logger
    leaves no on-disk artifact.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Filesystem path the logger writes to."""
        return self._path

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def log(self, event: str, **fields: Any) -> None:
        """Append one event record to the trace file.

        Args:
            event: Short event name (e.g. ``"turn_start"``,
                ``"model_complete"``, ``"tool_end"``).
            **fields: Arbitrary key/value pairs describing the event.
                Non-JSON-native values are coerced to strings.
        """
        record = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "event": event,
            **{k: _sanitize(v) for k, v in fields.items()},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def read_events(self) -> list[dict[str, Any]]:
        """Return every parseable event from the trace file in write order.

        A missing file yields an empty list. Lines that fail to parse are
        skipped silently — a single malformed line never poisons the
        whole log.
        """
        if not self._path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        for raw_line in raw.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
        return events

    def token_totals(self) -> dict[str, int]:
        """Sum token counts across every ``model_complete`` event.

        Returns:
            ``{"input_tokens": int, "output_tokens": int,
              "total_tokens": int, "model_calls": int}``.
            ``total_tokens`` is the sum of the LangChain-reported field
            when present, falling back to ``input + output``.
        """
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        model_calls = 0
        for event in self.read_events():
            if event.get("event") != "model_complete":
                continue
            model_calls += 1
            input_n = event.get("input_tokens")
            output_n = event.get("output_tokens")
            reported_total = event.get("total_tokens")
            if isinstance(input_n, int):
                input_tokens += input_n
            if isinstance(output_n, int):
                output_tokens += output_n
            if isinstance(reported_total, int):
                total_tokens += reported_total
            elif isinstance(input_n, int) and isinstance(output_n, int):
                total_tokens += input_n + output_n
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "model_calls": model_calls,
        }
