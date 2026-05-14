"""Rich-rendering helpers for LangGraph events.

DeepAgents' compiled graph emits a stream of events when driven via
``agent.astream_events(version="v2")``. The shapes of those events are
documented in LangChain's streaming docs; the ones Quoriv cares about
right now are:

    on_chat_model_stream    A token (or content chunk) from the LLM.
    on_tool_start           A tool call has begun. ``event["name"]`` is the
                            tool name; ``event["data"]["input"]`` are the
                            arguments.
    on_tool_end             A tool call has returned. ``event["data"]["output"]``
                            is the result.

These helpers stay deliberately small for Day 5 — Phase 1 will replace the
plain-text streamer with a markdown-aware Rich ``Live`` widget and add
diff rendering when ``edit_file`` is the tool in flight.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.console import Console


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------


def render_token(console: Console, text: str) -> None:
    """Print a streamed token from the LLM with no markup interpretation."""
    if text:
        console.out(text, end="", highlight=False)


def render_tool_start(console: Console, name: str, args: Any) -> None:  # event payload is dynamic
    """Render the header line for a tool call: name and compact args."""
    console.print(f"\n[dim cyan]→ {name}[/dim cyan]  [dim]{_format_args(args)}[/dim]")


def render_tool_end(
    console: Console,
    output: Any,  # event payload is dynamic
    *,
    max_len: int = 400,
) -> None:
    """Render a tool result, truncating long output for readability."""
    text = "" if output is None else str(output)
    if len(text) > max_len:
        text = text[:max_len] + "  …(truncated)"
    for line in text.splitlines() or [""]:
        console.print(f"[dim]  {line}[/dim]")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_args(args: Any, *, max_len: int = 120) -> str:
    """Compact ``key=repr(value)`` listing for a tool call's arguments."""
    if not isinstance(args, dict):
        return repr(args)
    parts: list[str] = []
    for key, value in args.items():
        value_repr = repr(value)
        if len(value_repr) > 50:
            value_repr = value_repr[:50] + "…"
        parts.append(f"{key}={value_repr}")
    rendered = ", ".join(parts)
    if len(rendered) > max_len:
        rendered = rendered[:max_len] + "…"
    return rendered
