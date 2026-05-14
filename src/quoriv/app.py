"""Interactive chat loop driving a DeepAgent.

Wiring summary:
    * Build a session-scoped :class:`CompiledStateGraph` via
      :func:`quoriv.core.agent.build_agent`. That agent has the full
      DeepAgents built-in toolset (write_todos, ls, read_file, write_file,
      edit_file, glob, grep, execute, task) plus always-on path protection.
    * Drive the agent via ``agent.astream_events(version="v2")`` and route
      events through :mod:`quoriv.core.events` for rendering.
    * Slice 7: :class:`AsyncSqliteSaver` rooted at ``<cwd>/.quoriv/sessions.db``
      persists conversational state across restarts. The opened saver is
      passed to :func:`build_agent` so the agent's checkpointer becomes
      the on-disk DB. A :class:`SessionRegistry` sidecar maps
      human-friendly names to ``thread_id`` values for the ``/save``,
      ``/load``, and ``/resume`` slash commands.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel

from quoriv import __version__
from quoriv.core import (
    SessionRegistry,
    build_agent,
    db_path,
    ensure_quoriv_dir,
    render_tool_end,
    render_tool_start,
)
from quoriv.models import MissingAPIKeyError
from quoriv.permissions import PermissionMode, is_read_only
from quoriv.ui import (
    ApprovalDecision,
    StreamRenderer,
    prompt_approval,
    render_edit_diff,
)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from quoriv.config import QuorivConfig

ALLOWED_MODES: tuple[PermissionMode, ...] = ("read-only", "ask", "auto", "yolo")


SLASH_COMMANDS: dict[str, str] = {
    "/help": "List available slash commands",
    "/clear": "Start a fresh conversation (new thread)",
    "/save": "Save the current thread under a name (default: first 8 chars of thread id)",
    "/load": "Switch to a saved thread by name (no arg lists saved sessions)",
    "/resume": "Switch to the most-recently-saved thread",
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

    Opens an :class:`AsyncSqliteSaver` at ``<cwd>/.quoriv/sessions.db``
    for the duration of the session. The saver is passed to the agent
    as its checkpointer so conversational state persists across
    restarts.

    Args:
        config: Loaded Quoriv configuration.
        model_override: Optional ``provider:name`` overriding
            ``config.model.default`` for this session.
        mode: Permission mode for this session — one of ``read-only`` /
            ``ask`` / ``auto`` / ``yolo``. Compiled to DeepAgents'
            ``interrupt_on=`` config by
            :func:`quoriv.permissions.interrupt_on_for_mode`.
        cwd: Repository root for the agent's filesystem and shell.
            Defaults to ``Path.cwd()``.
    """
    console = Console()
    model_id = model_override or config.model.default

    if mode not in ALLOWED_MODES:
        console.print(f"[red]Unknown mode {mode!r}.[/red]  Valid: {', '.join(ALLOWED_MODES)}")
        return
    permission_mode: PermissionMode = mode

    cwd_path = cwd if cwd is not None else Path.cwd()
    ensure_quoriv_dir(cwd_path)
    sessions_db = db_path(cwd_path)
    registry = SessionRegistry.for_cwd(cwd_path)

    async with AsyncSqliteSaver.from_conn_string(str(sessions_db)) as saver:
        try:
            agent = build_agent(
                config,
                model_override=model_override,
                cwd=cwd_path,
                mode=permission_mode,
                checkpointer=saver,
            )
        except MissingAPIKeyError as exc:
            _render_missing_key(console, exc)
            return
        except Exception as exc:  # pragma: no cover  # surfaces upstream errors
            console.print(f"[red]Failed to build agent for {model_id!r}:[/red] {exc}")
            return

        _render_welcome(console, model_id=model_id, mode=mode, cwd=cwd_path)
        await _interactive_loop(console, agent, registry, permission_mode)


async def _interactive_loop(
    console: Console,
    agent: Any,
    registry: SessionRegistry,
    permission_mode: PermissionMode,
) -> None:
    """Run the prompt → agent → render cycle until the user exits."""
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
            command_result = _handle_slash(console, user_input, thread_id, registry)
            if command_result.exit:
                return
            if command_result.new_thread_id is not None:
                thread_id = command_result.new_thread_id
            continue

        try:
            await _drive_turn(console, agent, user_input, thread_id, permission_mode)
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


def _handle_slash(  # noqa: PLR0911 — slash dispatch is a flat switch, one return per command
    console: Console,
    raw: str,
    current_thread_id: str,
    registry: SessionRegistry,
) -> _SlashResult:
    """Dispatch a slash command and return what the caller should do next."""
    parts = raw.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

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

    if cmd == "/save":
        return _handle_save(console, arg, current_thread_id, registry)

    if cmd == "/load":
        return _handle_load(console, arg, registry)

    if cmd == "/resume":
        return _handle_resume(console, registry)

    console.print(f"[red]Unknown command:[/red] {cmd}  (try [cyan]/help[/cyan])")
    return _SlashResult()


def _handle_save(
    console: Console,
    name_arg: str,
    current_thread_id: str,
    registry: SessionRegistry,
) -> _SlashResult:
    """Anchor the current thread under a user-supplied (or default) name."""
    name = name_arg or current_thread_id[:8]
    try:
        record = registry.save(name, current_thread_id)
    except ValueError as exc:
        console.print(f"[red]/save:[/red] {exc}")
        return _SlashResult()
    console.print(
        f"[green]Saved[/green] thread [cyan]{record.thread_id[:8]}[/cyan] "
        f"as [yellow]{record.name!r}[/yellow]."
    )
    return _SlashResult()


def _handle_load(
    console: Console,
    name_arg: str,
    registry: SessionRegistry,
) -> _SlashResult:
    """Switch to a saved thread by name, or list saved sessions if no name."""
    if not name_arg:
        _print_saved_sessions(console, registry)
        return _SlashResult()
    record = registry.load(name_arg)
    if record is None:
        console.print(f"[red]/load:[/red] no saved session named {name_arg!r}")
        return _SlashResult()
    console.print(
        f"[green]Loaded[/green] [yellow]{record.name!r}[/yellow] "
        f"(thread [cyan]{record.thread_id[:8]}[/cyan])."
    )
    return _SlashResult(new_thread_id=record.thread_id)


def _handle_resume(console: Console, registry: SessionRegistry) -> _SlashResult:
    """Switch to the most-recently-saved thread."""
    record = registry.most_recent()
    if record is None:
        console.print("[red]/resume:[/red] no saved sessions yet — use /save first")
        return _SlashResult()
    console.print(
        f"[green]Resumed[/green] [yellow]{record.name!r}[/yellow] "
        f"(thread [cyan]{record.thread_id[:8]}[/cyan])."
    )
    return _SlashResult(new_thread_id=record.thread_id)


def _print_saved_sessions(console: Console, registry: SessionRegistry) -> None:
    """Print a table of saved sessions, most-recent first."""
    sessions = registry.list_named()
    if not sessions:
        console.print(
            "[dim]No saved sessions yet. Use [cyan]/save [name][/cyan] to anchor "
            "the current thread.[/dim]"
        )
        return
    console.print()
    console.print("[bold]Saved sessions[/bold]")
    for s in sorted(sessions, key=lambda s: s.saved_at, reverse=True):
        console.print(
            f"  [yellow]{s.name}[/yellow]  [dim]{s.saved_at}[/dim]  [cyan]{s.thread_id[:8]}[/cyan]"
        )
    console.print()


# ---------------------------------------------------------------------------
# Agent driver
# ---------------------------------------------------------------------------


async def _drive_turn(
    console: Console,
    agent: Any,  # see core.agent.build_agent for the return-type rationale
    user_input: str,
    thread_id: str,
    mode: PermissionMode,
) -> None:
    """Drive one full user turn end-to-end, handling HITL interrupts.

    The loop:
        1. Stream events from the agent until the graph pauses or finishes.
        2. After the stream ends, ask the checkpointer whether the graph
           is parked on a :class:`HumanInTheLoopMiddleware` interrupt.
        3. If yes, render an approval prompt for each pending action and
           resume the graph with the user's decisions.
        4. Repeat until the agent has no more pending interrupts.
    """
    run_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    next_input: Any = {"messages": [HumanMessage(content=user_input)]}
    auto_deny = is_read_only(mode)

    while True:
        console.print()
        await _stream_events(console, agent, next_input, run_config)
        console.print()

        hitl_request = await _pending_hitl_request(agent, run_config)
        if hitl_request is None:
            return

        decisions = await _collect_decisions(console, hitl_request, auto_deny=auto_deny)
        next_input = Command(resume={"decisions": decisions})


async def _stream_events(
    console: Console,
    agent: Any,
    input_payload: Any,
    run_config: RunnableConfig,
) -> None:
    """Pump the agent's event stream into the UI.

    LLM tokens flow through a :class:`StreamRenderer` (markdown-aware via
    Rich ``Live``). Tool calls render separately — ``edit_file`` gets a
    colored unified diff via :func:`render_edit_diff`; other tools use
    the generic header line.
    """
    renderer = StreamRenderer(console)
    try:
        async for event in agent.astream_events(input_payload, config=run_config, version="v2"):
            kind = event.get("event")
            data = event.get("data", {})

            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk is None:
                    continue
                text = _chunk_text(getattr(chunk, "content", ""))
                renderer.push(text)
                continue

            if kind == "on_chat_model_end":
                renderer.finalize()
                continue

            if kind == "on_tool_start":
                renderer.finalize()
                name = event.get("name", "?")
                tool_args = data.get("input", {})
                if name == "edit_file" and isinstance(tool_args, dict):
                    render_edit_diff(
                        console,
                        file_path=str(tool_args.get("file_path", "")),
                        old_string=str(tool_args.get("old_string", "")),
                        new_string=str(tool_args.get("new_string", "")),
                    )
                else:
                    render_tool_start(console, name, tool_args)
                continue

            if kind == "on_tool_end":
                render_tool_end(console, data.get("output"))
                continue
    finally:
        renderer.finalize()


async def _pending_hitl_request(
    agent: Any,
    run_config: RunnableConfig,
) -> dict[str, Any] | None:
    """Return the first pending ``HITLRequest`` payload, or ``None``."""
    state = await agent.aget_state(run_config)
    for task in getattr(state, "tasks", ()):
        for interrupt in getattr(task, "interrupts", ()):
            payload = getattr(interrupt, "value", None)
            if isinstance(payload, dict) and "action_requests" in payload:
                return payload
    return None


async def _collect_decisions(
    console: Console,
    hitl_request: dict[str, Any],
    *,
    auto_deny: bool,
) -> list[dict[str, Any]]:
    """Prompt the user for each ``ActionRequest`` and serialize the decisions."""
    decisions: list[dict[str, Any]] = []
    for action in hitl_request.get("action_requests", []):
        decision = await prompt_approval(
            console,
            tool_name=action.get("name", "?"),
            tool_args=action.get("args", {}),
            description=action.get("description"),
            auto_deny=auto_deny,
        )
        decisions.append(_decision_payload(decision))
    return decisions


def _decision_payload(decision: ApprovalDecision) -> dict[str, Any]:
    """Convert an :class:`ApprovalDecision` to the HITL resume schema."""
    payload: dict[str, Any] = {"type": decision.type}
    if decision.message is not None:
        payload["message"] = decision.message
    return payload


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
