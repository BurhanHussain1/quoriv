"""Interactive chat loop driving a DeepAgent.

Day 5 wiring:
    * Build a session-scoped :class:`CompiledStateGraph` via
      :func:`quoriv.core.agent.build_agent`. That agent has the full
      DeepAgents built-in toolset (write_todos, ls, read_file, write_file,
      edit_file, glob, grep, execute, task) plus always-on path protection.
    * Drive the agent via ``agent.astream_events(version="v2")`` and route
      events through :mod:`quoriv.core.events` for rendering.
    * An in-memory checkpointer keyed by a per-session ``thread_id`` is the
      conversation state — no manual message-history bookkeeping needed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel

from quoriv import __version__
from quoriv.core import build_agent, render_token, render_tool_end, render_tool_start
from quoriv.models import MissingAPIKeyError

if TYPE_CHECKING:
    from pathlib import Path

    from langchain_core.runnables import RunnableConfig

    from quoriv.config import QuorivConfig
    from quoriv.permissions import PermissionMode

ALLOWED_MODES: tuple[PermissionMode, ...] = ("read-only", "ask", "auto", "yolo")


SLASH_COMMANDS: dict[str, str] = {
    "/help": "List available slash commands",
    "/clear": "Start a fresh conversation (new thread)",
    "/exit": "Exit the chat session",
    "/quit": "Exit the chat session (alias)",
}


async def run_chat(
    config: QuorivConfig,
    *,
    model_override: str | None = None,
    mode: str = "ask",
    cwd: Path | None = None,
) -> None:
    """Run the interactive chat loop until the user exits.

    Args:
        config: Loaded Quoriv configuration.
        model_override: Optional ``provider:name`` overriding
            ``config.model.default`` for this session.
        mode: Permission mode for this session — one of ``read-only`` /
            ``ask`` / ``auto`` / ``yolo``. Compiled to DeepAgents'
            ``interrupt_on=`` config by
            :func:`quoriv.permissions.interrupt_on_for_mode`.
        cwd: Repository root for the agent's filesystem and shell.
            Defaults to ``Path.cwd()`` (resolved inside ``build_agent``).
    """
    console = Console()
    model_id = model_override or config.model.default

    if mode not in ALLOWED_MODES:
        console.print(f"[red]Unknown mode {mode!r}.[/red]  Valid: {', '.join(ALLOWED_MODES)}")
        return
    permission_mode: PermissionMode = mode

    try:
        agent = build_agent(
            config,
            model_override=model_override,
            cwd=cwd,
            mode=permission_mode,
        )
    except MissingAPIKeyError as exc:
        _render_missing_key(console, exc)
        return
    except Exception as exc:  # pragma: no cover  # surfaces upstream errors
        console.print(f"[red]Failed to build agent for {model_id!r}:[/red] {exc}")
        return

    _render_welcome(console, model_id=model_id, mode=mode, cwd=cwd)

    session: PromptSession[str] = PromptSession()
    thread_id = _new_thread_id()

    while True:
        try:
            user_input = await session.prompt_async(HTML("<ansigreen>></ansigreen> "))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            return

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            command_result = _handle_slash(console, user_input, thread_id)
            if command_result.exit:
                return
            if command_result.new_thread_id is not None:
                thread_id = command_result.new_thread_id
            continue

        try:
            await _stream_agent(console, agent, user_input, thread_id)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            continue
        except Exception as exc:  # surface agent/network errors gracefully
            console.print(f"\n[red]Error:[/red] {exc}")
            continue


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_welcome(
    console: Console,
    *,
    model_id: str,
    mode: str,
    cwd: Path | None,
) -> None:
    cwd_display = str(cwd) if cwd is not None else "(current directory)"
    console.print(
        Panel.fit(
            (
                f"[bold]Quoriv[/bold] v{__version__}\n"
                f"Model: [cyan]{model_id}[/cyan]\n"
                f"Mode:  [cyan]{mode}[/cyan]\n"
                f"Root:  [cyan]{cwd_display}[/cyan]\n"
                f"Type [yellow]/help[/yellow] for commands, [yellow]/exit[/yellow] to quit."
            ),
            title="welcome",
            border_style="cyan",
        )
    )


def _render_missing_key(console: Console, exc: MissingAPIKeyError) -> None:
    console.print(f"\n[red]No API key found for provider {exc.provider!r}.[/red]\n")
    console.print("Configure one of the following:")
    console.print(f"  • Run:    [cyan]quoriv config set {exc.provider}[/cyan]")
    console.print(f"  • Or set: [cyan]${exc.env_var}=<your-key>[/cyan] in the environment\n")


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


class _SlashResult:
    """Outcome of dispatching a slash command."""

    __slots__ = ("exit", "new_thread_id")

    def __init__(self, *, exit: bool = False, new_thread_id: str | None = None) -> None:
        self.exit = exit
        self.new_thread_id = new_thread_id


def _handle_slash(console: Console, raw: str, current_thread_id: str) -> _SlashResult:
    """Dispatch a slash command and return what the caller should do next."""
    cmd = raw.split(maxsplit=1)[0].lower()

    if cmd in ("/exit", "/quit"):
        console.print("[dim]Goodbye.[/dim]")
        return _SlashResult(exit=True)

    if cmd == "/clear":
        new_id = _new_thread_id()
        console.clear()
        console.print("[dim]Started a fresh conversation.[/dim]")
        return _SlashResult(new_thread_id=new_id)

    if cmd == "/help":
        console.print()
        for c, desc in SLASH_COMMANDS.items():
            console.print(f"  [cyan]{c:<8}[/cyan]  {desc}")
        console.print()
        return _SlashResult()

    console.print(f"[red]Unknown command:[/red] {cmd}  (try [cyan]/help[/cyan])")
    _ = current_thread_id  # placeholder for future thread-aware commands
    return _SlashResult()


# ---------------------------------------------------------------------------
# Agent driver
# ---------------------------------------------------------------------------


async def _stream_agent(
    console: Console,
    agent: Any,  # see core.agent.build_agent for the return-type rationale
    user_input: str,
    thread_id: str,
) -> None:
    """Drive the agent with the user's input and render the event stream.

    The DeepAgent's ``MemorySaver`` checkpointer accumulates conversation
    state under ``thread_id``; we only send the new user turn each call.
    """
    run_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    console.print()  # blank line before output

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=user_input)]},
        config=run_config,
        version="v2",
    ):
        kind = event.get("event")
        data = event.get("data", {})

        if kind == "on_chat_model_stream":
            chunk = data.get("chunk")
            if chunk is None:
                continue
            text = _chunk_text(getattr(chunk, "content", ""))
            render_token(console, text)
            continue

        if kind == "on_tool_start":
            name = event.get("name", "?")
            tool_args = data.get("input", {})
            render_tool_start(console, name, tool_args)
            continue

        if kind == "on_tool_end":
            render_tool_end(console, data.get("output"))
            continue

    console.print()  # final newline after the stream completes


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _new_thread_id() -> str:
    """Return a fresh checkpointer thread identifier for a session."""
    return uuid.uuid4().hex


def _chunk_text(content: Any) -> str:  # LangChain content is dynamic
    """Extract plain text from a LangChain message chunk's ``content`` field.

    Most chunks carry a string. Multimodal / tool-use chunks may instead
    carry a list of content blocks — we surface text blocks and ignore the
    rest at this layer.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)
