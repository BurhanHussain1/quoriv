"""Replay viewer for saved chat threads — Phase 3 Slice 12.

Every chat session writes a per-thread JSONL trace log (see
:class:`quoriv.observability.TraceLogger`). ``quoriv replay`` reads
that log back and renders the events in human-readable form so you
can post-mortem what the agent did without re-invoking any LLM.

The viewer is **read-only** — no model calls, no shell, no tool
execution. It walks ``read_events()`` and prints each record with
a tag matching its kind:

    turn_start       cyan ``▶`` prefix + user input
    model_complete   dim header + token totals
    tool_start       yellow ``↳`` prefix + tool name + args
    tool_end         green ``◀`` prefix + truncated output preview
    turn_end         cyan ``■`` prefix
    *                fall-through plain JSON dump

Tool names that match :func:`render_edit_diff`-style events keep their
header line — the original ``edit_file`` diff isn't recoverable from
the trace (we only stored ``args``), so we just show the args dict.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from quoriv.observability import TraceLogger

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console


_EVENT_PREFIXES: dict[str, tuple[str, str]] = {
    "turn_start": ("[cyan]▶[/cyan]", "turn start"),
    "model_complete": ("[dim]·[/dim]", "model complete"),
    "tool_start": ("[yellow]↳[/yellow]", "tool start"),
    "tool_end": ("[green]◀[/green]", "tool end"),
    "turn_end": ("[cyan]■[/cyan]", "turn end"),
}
"""Per-event-kind visual prefix and short label."""


def _format_record(event: dict[str, Any]) -> str:
    """Format one trace event into a single Rich-markup line.

    Unknown event kinds fall back to a compact JSON dump so we never
    silently drop information the user might care about.
    """
    kind = event.get("event", "?")
    timestamp = event.get("timestamp", "")
    short_ts = timestamp[11:19] if isinstance(timestamp, str) and len(timestamp) >= 19 else ""
    prefix_marker, label = _EVENT_PREFIXES.get(kind, ("[dim]?[/dim]", kind))

    if kind == "turn_start":
        user_input = event.get("user_input", "")
        mode = event.get("mode", "")
        return (
            f"{prefix_marker} [bold]{label}[/bold] "
            f"[dim]{short_ts} mode={mode}[/dim]\n    {user_input}"
        )
    if kind == "model_complete":
        model = event.get("model", "?")
        ti = event.get("input_tokens", "?")
        to = event.get("output_tokens", "?")
        return f"{prefix_marker} [dim]{label} {short_ts} model={model} in={ti} out={to}[/dim]"
    if kind == "tool_start":
        tool_name = event.get("tool_name", "?")
        args = event.get("args", {})
        return (
            f"{prefix_marker} [bold]{label}[/bold] [cyan]{tool_name}[/cyan] "
            f"[dim]{short_ts}[/dim]\n    [dim]args={json.dumps(args)[:200]}[/dim]"
        )
    if kind == "tool_end":
        tool_name = event.get("tool_name", "?")
        preview = event.get("output_preview", "")
        return (
            f"{prefix_marker} [bold]{label}[/bold] [cyan]{tool_name}[/cyan] "
            f"[dim]{short_ts}[/dim]\n    [dim]{str(preview)[:200]}[/dim]"
        )
    if kind == "turn_end":
        return f"{prefix_marker} [bold]{label}[/bold] [dim]{short_ts}[/dim]"
    return f"{prefix_marker} [dim]{label} {short_ts}[/dim] [dim]{json.dumps(event)[:200]}[/dim]"


def replay_thread(console: Console, trace_path: Path) -> int:
    """Read ``trace_path`` and print every event to ``console``.

    Args:
        console: Rich console used for rendering.
        trace_path: Path to a per-thread JSONL trace file.

    Returns:
        The number of events rendered. ``0`` when the file is missing
        or empty — the caller decides how to message that.
    """
    logger = TraceLogger(trace_path)
    events = logger.read_events()
    if not events:
        console.print(f"[dim]No events in {trace_path}.[/dim]")
        return 0
    console.print()
    console.print(f"[bold]Replay[/bold] [cyan]{trace_path}[/cyan]")
    console.print(f"[dim]({len(events)} events)[/dim]")
    console.print()
    for record in events:
        console.print(_format_record(record))
    console.print()
    return len(events)
