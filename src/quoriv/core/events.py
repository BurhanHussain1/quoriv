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

Phase 5 Slice 6 (v1.5.7) — Claude-Code-style tool feedback:

* Each tool gets a short, contextual one-line label instead of a raw
  ``name(arg=value, ...)`` dump. ``read_file(file_path="/a.py")`` becomes
  ``• Reading /a.py``; ``ls(path="/")`` becomes ``• Listing /``.
* Tool output is *not* re-rendered to the chat by default — the agent's
  next message already summarises what it found. The only exceptions
  are ``write_todos`` (rendered as a checkbox list inline so the user
  can follow progress) and ``execute`` (the shell output is usually
  what the user wants to see).
* ``edit_file`` / ``write_file`` keep their existing custom renderers
  in ``quoriv.ui.diff`` — they short-circuit before reaching the
  generic helpers here.

The compact rendering matches Claude Code's "Reading FOO.py", "Running
pytest", "Editing index.ts" status lines: enough context to know what
the agent is doing without burying the conversation in raw arg/output
JSON.
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


def render_tool_start(console: Console, name: str, args: Any) -> None:
    """Render a one-line, human-readable label for a tool invocation.

    Special cases:
        ``write_todos``  Renders the todo list as checkboxes inline so
                         the user can follow the agent's plan.
        ``edit_file`` /
        ``write_file``   App.py calls ``render_edit_diff`` instead of
                         this helper; no-op fallback here just in case.
    """
    if name == "write_todos":
        render_todos(console, args)
        return

    label = _tool_label(name, args)
    console.print(f"[dim cyan]•[/dim cyan] [dim]{label}[/dim]")


def render_tool_end(
    console: Console,
    output: Any,
    *,
    name: str = "",
    max_len: int = 400,
) -> None:
    """Render a tool result.

    Default behaviour is **silent** — most tool output is for the agent
    to consume, not the user. The agent's next message will summarise
    what it found. Two exceptions:

    * ``execute`` — shell command output is typically the point of the
      call, so show it (compact, truncated).
    * Unknown tools or when ``name`` is empty fall back to the legacy
      "dim-quoted excerpt" rendering so we don't silently swallow
      output from custom tools.
    """
    if name == "write_todos":
        # Already rendered by render_tool_start; the tool's return
        # value is just an echo of the same state.
        return

    if name in {"read_file", "ls", "glob", "grep"}:
        # The agent will quote the parts it cares about in its next
        # message. Don't double-print.
        return

    if name == "execute":
        _render_execute_output(console, output, max_len=max_len)
        return

    if name and name not in {"", "task"}:
        # Other tools (web_search, web_fetch, ast_*, git_*, MCP tools)
        # — show a short truncated excerpt so the user can spot
        # failures.
        text = "" if output is None else str(output).strip()
        if not text:
            return
        if len(text) > max_len:
            text = text[:max_len] + "  …(truncated)"
        first_line = text.splitlines()[0] if text else ""
        if len(first_line) > 100:
            first_line = first_line[:100] + "…"
        console.print(f"  [dim]{first_line}[/dim]")
        return

    # Legacy fallback for callers that don't pass ``name`` (older tests).
    text = "" if output is None else str(output)
    if len(text) > max_len:
        text = text[:max_len] + "  …(truncated)"
    for line in text.splitlines() or [""]:
        console.print(f"[dim]  {line}[/dim]")


# ---------------------------------------------------------------------------
# Todo list rendering (DeepAgents' write_todos)
# ---------------------------------------------------------------------------


def render_todos(console: Console, args: Any) -> None:
    """Render the agent's todo list as a checkbox section.

    DeepAgents' ``write_todos`` tool accepts a list under
    ``args["todos"]``. Each entry is a dict with ``content`` and a
    ``status`` of ``"pending"`` / ``"in_progress"`` / ``"completed"``
    (the markdown-style todo schema from
    :class:`langchain.agents.middleware.TodoListMiddleware`).

    Output looks like::

        Plan
          [x] Read the existing file
          [~] Draft the helper
          [ ] Wire it into the entry point

    Empty / malformed lists fall back to the generic tool-call label
    so the user always sees *something* happening.
    """
    todos = _extract_todos(args)
    if not todos:
        # Defensive fallback — shape changed or tool was called with
        # no list. Show the generic label so the user isn't confused
        # by a silent tool call.
        console.print("[dim cyan]•[/dim cyan] [dim]Updating todo list[/dim]")
        return

    console.print()
    console.print("[bold cyan]Plan[/bold cyan]")
    for todo in todos:
        content = str(todo.get("content", "")).strip()
        if not content:
            continue
        status = str(todo.get("status", "pending")).lower()
        marker, style = _todo_marker(status)
        console.print(f"  {marker} [{style}]{content}[/{style}]")
    console.print()


# ---------------------------------------------------------------------------
# Per-tool label table
# ---------------------------------------------------------------------------


def _tool_label(name: str, args: Any) -> str:  # noqa: PLR0911, PLR0912 — flat per-tool dispatch
    """Build the one-line "what is the agent doing" label for a tool call."""
    args_dict = args if isinstance(args, dict) else {}

    if name == "ls":
        return f"Listing {args_dict.get('path', '/') or '/'}"
    if name == "read_file":
        path = args_dict.get("file_path") or args_dict.get("path") or "?"
        return f"Reading {path}"
    if name == "write_file":
        # write_file usually goes through the diff renderer in app.py,
        # but a defensive label here in case it doesn't.
        path = args_dict.get("file_path") or args_dict.get("path") or "?"
        return f"Writing {path}"
    if name == "edit_file":
        path = args_dict.get("file_path") or args_dict.get("path") or "?"
        return f"Editing {path}"
    if name == "glob":
        pattern = args_dict.get("pattern") or args_dict.get("glob") or "?"
        return f"Searching files matching {pattern}"
    if name == "grep":
        pattern = args_dict.get("pattern") or "?"
        return f"Searching for {pattern!r}"
    if name == "execute":
        cmd = args_dict.get("command") or args_dict.get("cmd") or "?"
        cmd_str = str(cmd)
        if len(cmd_str) > 80:
            cmd_str = cmd_str[:80] + "…"
        return f"Running [white]{cmd_str}[/white]"
    if name == "task":
        agent = args_dict.get("subagent_name") or args_dict.get("subagent") or "subagent"
        desc = args_dict.get("description") or args_dict.get("task") or ""
        if desc:
            desc_str = str(desc)
            if len(desc_str) > 60:
                desc_str = desc_str[:60] + "…"
            return f"Delegating to {agent}: {desc_str}"
        return f"Delegating to {agent}"
    if name == "web_search":
        query = args_dict.get("query") or args_dict.get("q") or "?"
        return f"Searching the web for {query!r}"
    if name == "web_fetch":
        url = args_dict.get("url") or "?"
        return f"Fetching {url}"

    # Generic tool (custom Quoriv tools, MCP, etc.) — show the name
    # plus a compact arg summary so the user still has context.
    return f"{name} {_format_args(args_dict)}".strip()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_todos(args: Any) -> list[dict[str, Any]]:
    """Pull the todo list out of a ``write_todos`` payload.

    Handles a few possible shapes defensively:
        * ``{"todos": [{"content": ..., "status": ...}, ...]}``  (canonical)
        * ``{"todos": ["string", ...]}``                          (string list)
        * ``[{"content": ..., ...}, ...]``                        (bare list)
    """
    raw: Any = args.get("todos", args) if isinstance(args, dict) else args

    if not isinstance(raw, list):
        return []

    todos: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            todos.append(item)
        elif isinstance(item, str):
            todos.append({"content": item, "status": "pending"})
    return todos


def _todo_marker(status: str) -> tuple[str, str]:
    """Map a todo status to ``(marker, rich-style)``."""
    if status in {"completed", "done", "complete"}:
        return ("[green]\\[x][/green]", "green strike")
    if status in {"in_progress", "in-progress", "doing", "active"}:
        return ("[yellow]\\[~][/yellow]", "yellow bold")
    return ("[dim]\\[ ][/dim]", "white")


def _render_execute_output(console: Console, output: Any, *, max_len: int) -> None:
    """Render the result of a shell ``execute`` call compactly.

    DeepAgents returns an ``ExecuteResponse`` (``output``, ``exit_code``,
    ``truncated``). Show the first ~10 lines, indented. Non-zero exit
    codes get flagged in red so failures aren't easy to miss.
    """
    output_text = ""
    exit_code: int | None = None

    if isinstance(output, dict):
        output_text = str(output.get("output", "") or "")
        exit_code = output.get("exit_code")
    elif hasattr(output, "output"):  # ExecuteResponse dataclass / pydantic
        output_text = str(getattr(output, "output", "") or "")
        exit_code = getattr(output, "exit_code", None)
    else:
        output_text = "" if output is None else str(output)

    text = output_text.strip()
    if not text:
        if exit_code is not None and exit_code != 0:
            console.print(f"  [red]exit {exit_code}[/red]")
        return

    if len(text) > max_len:
        text = text[:max_len] + "  …(truncated)"

    lines = text.splitlines()
    display_max = 10
    visible = lines[:display_max]
    for line in visible:
        console.print(f"  [dim]{line}[/dim]")
    if len(lines) > display_max:
        console.print(f"  [dim]… +{len(lines) - display_max} more lines[/dim]")
    if exit_code is not None and exit_code != 0:
        console.print(f"  [red]exit {exit_code}[/red]")


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
