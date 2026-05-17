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
    * Slice 8: persistent bottom status line (``model | mode | cwd |
      thread``) and four new read-only slash commands — ``/tools``,
      ``/memory``, ``/mode``, ``/cost``. ``/cost`` is wired to the Slice
      9 trace log; the other three introspect live session state.
    * Slice 9: per-thread JSONL trace log via
      :class:`quoriv.observability.TraceLogger`. ``_drive_turn`` records
      ``turn_start`` / ``turn_end`` and ``_stream_events`` records
      ``model_complete`` (with token usage when LangChain provides it),
      ``tool_start``, and ``tool_end``. ``/cost`` reads the active
      thread's log for token totals.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage
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
    memory_candidates,
    render_tool_end,
    render_tool_start,
    resolve_memory_files,
    trace_path,
)
from quoriv.models import MissingAPIKeyError
from quoriv.observability import (
    ProviderRate,
    TraceLogger,
    effective_rates,
    estimate_cost,
    lookup_rate,
)
from quoriv.permissions import (
    PermissionMode,
    SessionAllowlist,
    interrupt_on_for_mode,
    is_read_only,
)
from quoriv.tools import QUORIV_TOOLS
from quoriv.ui import (
    ApprovalDecision,
    StreamRenderer,
    prompt_approval,
    render_edit_diff,
)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from quoriv.config import QuorivConfig

ALLOWED_MODES: tuple[PermissionMode, ...] = ("read-only", "ask", "auto", "yolo")


SLASH_COMMANDS: dict[str, str] = {
    "/help": "List available slash commands",
    "/clear": "Start a fresh conversation (new thread)",
    "/save": "Save the current thread under a name (default: first 8 chars of thread id)",
    "/load": "Switch to a saved thread by name (no arg lists saved sessions)",
    "/resume": "Switch to the most-recently-saved thread",
    "/tools": "List the tools the agent has available",
    "/memory": "Show the status of memory files (~/.quoriv/memory.md, ./PROJECT.md)",
    "/mode": "Show permission mode (no arg) or live-switch (/mode <name>)",
    "/cost": "Show approximate session cost (token tracking lands in Slice 9)",
    "/exit": "Exit the chat session",
    "/quit": "Exit the chat session (alias)",
}


# DeepAgents' built-in tools (invisible behind the compiled-graph abstraction,
# so we list them by hand for ``/tools``). Mirrors what
# :func:`deepagents.create_deep_agent` registers via ``FilesystemMiddleware`` /
# ``LocalShellBackend`` / ``TodoMiddleware`` / ``SubAgentMiddleware``.
_DEEPAGENTS_BUILTIN_TOOLS: tuple[tuple[str, str], ...] = (
    ("write_todos", "Track and update the agent's structured todo list"),
    ("ls", "List files and directories"),
    ("read_file", "Read a file's contents"),
    ("write_file", "Create or overwrite a file"),
    ("edit_file", "Edit a file via search-and-replace"),
    ("glob", "Find files by glob pattern"),
    ("grep", "Literal-substring search of file contents"),
    ("execute", "Run a shell command in the working directory"),
    ("task", "Delegate work to a sub-agent"),
)


_MODE_DESCRIPTIONS: dict[PermissionMode, str] = {
    "read-only": "Investigation only — every write / shell call is auto-denied at the prompt.",
    "ask": "Prompt before every write_file / edit_file / git write / shell call.",
    "auto": "Auto-run file/git writes; prompt only before shell execution.",
    "yolo": "No prompts. Use with care.",
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
        await _interactive_loop(
            console,
            agent,
            registry,
            permission_mode,
            model_id=model_id,
            cwd=cwd_path,
            cost_rates=effective_rates(config),
            config=config,
            model_override=model_override,
            checkpointer=saver,
        )


async def _interactive_loop(
    console: Console,
    agent: Any,
    registry: SessionRegistry,
    permission_mode: PermissionMode,
    *,
    model_id: str,
    cwd: Path,
    cost_rates: dict[str, ProviderRate] | None = None,
    config: QuorivConfig | None = None,
    model_override: str | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> None:
    """Run the prompt → agent → render cycle until the user exits.

    Slice 8b: ``config``, ``model_override`` and ``checkpointer`` are
    captured so ``/mode <name>`` can rebuild the compiled agent in
    place via :func:`quoriv.core.build_agent` while reusing the same
    checkpointer — the running thread's state survives the switch.
    They default to ``None`` to keep older callers and tests that drive
    a single fixed mode working without modification.
    """
    thread_id = _new_thread_id()
    tracer = TraceLogger(trace_path(cwd, thread_id))
    # Phase 2 Slice 3: per-session allowlist. Lives for the whole
    # ``run_chat`` invocation and survives ``/clear`` (the user
    # promoted these tools deliberately; rotating the thread shouldn't
    # silently un-promote them).
    allowlist = SessionAllowlist()

    def _toolbar() -> str:
        # Closure reads the latest ``thread_id`` and ``permission_mode``
        # because Python closures resolve names at call time, not
        # definition time — so a live ``/mode`` switch is reflected on
        # the status line on the very next prompt redraw.
        return _build_status_line(
            model_id=model_id,
            mode=permission_mode,
            cwd=cwd,
            thread_id=thread_id,
        )

    session: PromptSession[str] = PromptSession(bottom_toolbar=_toolbar)

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
            command_result = _handle_slash(
                console,
                user_input,
                thread_id,
                registry,
                model_id=model_id,
                cwd=cwd,
                mode=permission_mode,
                tracer=tracer,
                cost_rates=cost_rates,
            )
            if command_result.exit:
                return
            if command_result.new_thread_id is not None:
                thread_id = command_result.new_thread_id
                # New thread → new trace file. The old logger is dropped;
                # its file remains on disk for ``/cost`` against the prior
                # thread (loadable via ``/load <name>`` later).
                tracer = TraceLogger(trace_path(cwd, thread_id))
            if command_result.new_mode is not None:
                # Slice 8b: live mode switch. Rebuild the compiled agent
                # against the same checkpointer so the running thread's
                # state is unaffected — only the ``interrupt_on=`` dict
                # changes. Falling back to the existing agent if any
                # required wiring is missing keeps legacy callers that
                # never pass ``config``/``checkpointer`` working.
                new_mode = command_result.new_mode
                if config is not None:
                    agent = build_agent(
                        config,
                        model_override=model_override,
                        cwd=cwd,
                        mode=new_mode,
                        checkpointer=checkpointer,
                    )
                permission_mode = new_mode
                console.print(
                    f"[green]Permission mode switched to[/green] [cyan]{permission_mode}[/cyan]."
                )
            continue

        try:
            await _drive_turn(
                console,
                agent,
                user_input,
                thread_id,
                permission_mode,
                tracer=tracer,
                allowlist=allowlist,
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            continue
        except Exception as exc:  # surface agent/network errors gracefully
            console.print(f"\n[red]Error:[/red] {exc}")
            continue


def _build_status_line(
    *,
    model_id: str,
    mode: PermissionMode,
    cwd: Path,
    thread_id: str,
) -> str:
    """Format the persistent bottom-toolbar string.

    Kept a pure function so it can be unit-tested directly without
    spinning up a :class:`PromptSession`.
    """
    return f" {model_id} | mode={mode} | {cwd.name or str(cwd)} | thread={thread_id[:8]} "


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
    # Phase 2 Slice 1: surface the memory files the agent has actually
    # loaded — silent when none exist, so users without a PROJECT.md
    # don't see a clutter line.
    loaded = resolve_memory_files(cwd if cwd is not None else Path.cwd())
    memory_line = ""
    if loaded:
        names = ", ".join(p.name for p in loaded)
        memory_line = f"Memory: [cyan]{names}[/cyan]\n"
    console.print(
        Panel.fit(
            (
                f"[bold]Quoriv[/bold] v{__version__}\n"
                f"Model: [cyan]{model_id}[/cyan]\n"
                f"Mode:  [cyan]{mode}[/cyan]\n"
                f"Root:  [cyan]{cwd_display}[/cyan]\n"
                f"{memory_line}"
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

    __slots__ = ("exit", "new_mode", "new_thread_id")

    def __init__(
        self,
        *,
        exit: bool = False,
        new_thread_id: str | None = None,
        new_mode: PermissionMode | None = None,
    ) -> None:
        self.exit = exit
        self.new_thread_id = new_thread_id
        # Slice 8b: ``/mode <name>`` returns a ``_SlashResult`` with
        # ``new_mode`` set; the interactive loop rebuilds the compiled
        # agent in place against the same checkpointer so the running
        # thread state survives the switch.
        self.new_mode = new_mode


def _handle_slash(  # noqa: PLR0911 — slash dispatch is a flat switch, one return per command
    console: Console,
    raw: str,
    current_thread_id: str,
    registry: SessionRegistry,
    *,
    model_id: str = "(unset)",
    cwd: Path | None = None,
    mode: PermissionMode = "ask",
    tracer: TraceLogger | None = None,
    cost_rates: dict[str, ProviderRate] | None = None,
) -> _SlashResult:
    """Dispatch a slash command and return what the caller should do next.

    The keyword-only context parameters (``model_id``, ``cwd``, ``mode``,
    ``tracer``, ``cost_rates``) feed the Slice 8 + Slice 9 introspection
    commands (``/tools`` / ``/memory`` / ``/mode`` / ``/cost``). They
    carry safe defaults so legacy call sites and tests that pre-date
    these slices still work without modification. ``cost_rates`` is the
    merged effective rate table (built-ins + user ``cost.rates``
    overrides); ``None`` falls back to the built-in :data:`RATES` for
    ``/cost``.
    """
    parts = raw.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    effective_cwd = cwd if cwd is not None else Path.cwd()

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

    if cmd == "/tools":
        return _handle_tools(console)

    if cmd == "/memory":
        return _handle_memory(console, effective_cwd)

    if cmd == "/mode":
        return _handle_mode(console, mode, arg)

    if cmd == "/cost":
        return _handle_cost(console, tracer, model_id=model_id, cost_rates=cost_rates)

    console.print(f"[red]Unknown command:[/red] {cmd}  (try [cyan]/help[/cyan])")
    return _SlashResult()


# ---------------------------------------------------------------------------
# Slice 8 — introspection helpers (/tools, /memory, /mode, /cost).
# ---------------------------------------------------------------------------


def _handle_tools(console: Console) -> _SlashResult:
    """List the tools the agent has available, grouped by origin."""
    console.print()
    console.print("[bold]DeepAgents built-ins[/bold]")
    for name, desc in _DEEPAGENTS_BUILTIN_TOOLS:
        console.print(f"  [cyan]{name:<12}[/cyan]  {desc}")
    console.print()
    console.print("[bold]Quoriv tools[/bold]")
    for tool in QUORIV_TOOLS:
        description = (getattr(tool, "description", "") or "").splitlines()
        summary = description[0] if description else ""
        console.print(f"  [cyan]{tool.name:<12}[/cyan]  {summary}")
    console.print()
    return _SlashResult()


def _handle_memory(console: Console, cwd: Path) -> _SlashResult:
    """Show the status of memory files the agent loads.

    Phase 2 Slice 1: when a candidate file exists, the agent's
    ``MemoryMiddleware`` has already loaded it into the system prompt
    at session start — the ``(loaded)`` tag makes that contract
    visible. Files that aren't on disk are still listed so the user
    knows where to drop them.
    """
    console.print()
    console.print("[bold]Memory files[/bold]")
    any_present = False
    for candidate in memory_candidates(cwd):
        if candidate.path.is_file():
            any_present = True
            size = candidate.path.stat().st_size
            console.print(
                f"  [green]✓[/green] {candidate.label:<8}  "
                f"[cyan]{candidate.path}[/cyan]  "
                f"[dim]({size} bytes)[/dim]  [green](loaded)[/green]"
            )
        else:
            console.print(
                f"  [dim]·[/dim] {candidate.label:<8}  "
                f"[dim]{candidate.path}[/dim]  [dim](not present)[/dim]"
            )
    if not any_present:
        console.print("[dim]No memory files found. Create one of the paths above and the[/dim]")
        console.print("[dim]agent will load it on next session start.[/dim]")
    console.print()
    return _SlashResult()


def _handle_mode(console: Console, mode: PermissionMode, arg: str = "") -> _SlashResult:
    """Show the active permission mode, or live-switch to a new one.

    Slice 8b: ``/mode <name>`` rebuilds the compiled agent in place
    against the same checkpointer, so the running thread's
    conversational state survives the switch. ``/mode`` with no
    argument keeps the original Slice 8 behavior — print the current
    mode, the tools it gates, and the menu of alternatives.
    """
    if arg:
        new_mode_arg = arg.strip().lower()
        if new_mode_arg not in ALLOWED_MODES:
            console.print()
            console.print(
                f"[red]/mode:[/red] unknown mode [yellow]{new_mode_arg!r}[/yellow].  "
                f"Valid: {', '.join(ALLOWED_MODES)}"
            )
            console.print()
            return _SlashResult()
        if new_mode_arg == mode:
            console.print()
            console.print(f"[dim]Already in [cyan]{mode}[/cyan] mode — no change.[/dim]")
            console.print()
            return _SlashResult()
        # mypy narrows new_mode_arg to PermissionMode after the
        # ``new_mode_arg not in ALLOWED_MODES`` guard above.
        new_mode: PermissionMode = new_mode_arg
        return _SlashResult(new_mode=new_mode)

    gated = sorted(interrupt_on_for_mode(mode))
    console.print()
    console.print(f"[bold]Permission mode[/bold]: [cyan]{mode}[/cyan]")
    console.print(f"  {_MODE_DESCRIPTIONS[mode]}")
    if gated:
        console.print(f"  Currently gates: [yellow]{', '.join(gated)}[/yellow]")
    else:
        console.print("  Currently gates: [dim](nothing — every tool runs without prompting)[/dim]")
    console.print()
    console.print("[bold]Available modes[/bold]")
    for name, desc in _MODE_DESCRIPTIONS.items():
        marker = "[green]●[/green]" if name == mode else "[dim]○[/dim]"
        console.print(f"  {marker} [cyan]{name:<10}[/cyan] {desc}")
    console.print()
    console.print(
        "[dim]Switch live with [cyan]/mode <name>[/cyan] "
        "(rebuilds the agent against the same thread).[/dim]"
    )
    console.print()
    return _SlashResult()


def _handle_cost(
    console: Console,
    tracer: TraceLogger | None,
    *,
    model_id: str = "(unset)",
    cost_rates: dict[str, ProviderRate] | None = None,
) -> _SlashResult:
    """Show token totals + dollar estimate for the active thread.

    ``cost_rates`` is the merged effective rate table (built-ins + user
    ``cost.rates`` overrides). ``None`` falls back to the built-in
    :data:`quoriv.observability.cost.RATES` so the help-style call sites
    in older tests keep working.
    """
    console.print()
    if tracer is None:
        # Called outside a chat loop (e.g., from a test) — nothing to read.
        console.print("[dim]No trace logger attached to this session.[/dim]")
        console.print()
        return _SlashResult()
    totals = tracer.token_totals()
    if totals["model_calls"] == 0:
        console.print(
            "[dim]No model calls recorded for this thread yet. Send a message first.[/dim]"
        )
        console.print(f"[dim]Trace file: {tracer.path}[/dim]")
        console.print()
        return _SlashResult()
    console.print("[bold]Token usage (this thread)[/bold]")
    console.print(f"  Input:  [cyan]{totals['input_tokens']:>8}[/cyan]")
    console.print(f"  Output: [cyan]{totals['output_tokens']:>8}[/cyan]")
    console.print(f"  Total:  [cyan]{totals['total_tokens']:>8}[/cyan]")
    console.print(f"  Calls:  [cyan]{totals['model_calls']:>8}[/cyan]")

    # Slice 9c: dollar cost estimate when the model_id is in the rate table.
    # Slice 9d: ``cost_rates`` is the effective table after merging the user's
    # ``cost.rates`` overrides over the built-in :data:`RATES`.
    rate = lookup_rate(model_id, cost_rates)
    if rate is None:
        console.print()
        console.print(f"[dim]No rate configured for model [cyan]{model_id}[/cyan] —[/dim]")
        console.print(
            '[dim]add a [cyan][cost.rates."{provider}:{model}"][/cyan] entry '
            "to [cyan]~/.quoriv/config.toml[/cyan] with the per-1k-token price.[/dim]"
        )
    else:
        costs = estimate_cost(rate, totals["input_tokens"], totals["output_tokens"])
        console.print()
        console.print(f"[bold]Estimated cost[/bold] (model: [cyan]{model_id}[/cyan])")
        console.print(f"  Input:  [green]${costs['input_cost_usd']:.4f}[/green]")
        console.print(f"  Output: [green]${costs['output_cost_usd']:.4f}[/green]")
        console.print(f"  Total:  [green]${costs['total_cost_usd']:.4f}[/green]")
        console.print(
            "[dim]Rates are approximate; update the table when provider pricing changes.[/dim]"
        )
    console.print(f"[dim]Trace file: {tracer.path}[/dim]")
    console.print()
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
    *,
    tracer: TraceLogger | None = None,
    allowlist: SessionAllowlist | None = None,
) -> None:
    """Drive one full user turn end-to-end, handling HITL interrupts.

    The loop:
        1. Stream events from the agent until the graph pauses or finishes.
        2. After the stream ends, ask the checkpointer whether the graph
           is parked on a :class:`HumanInTheLoopMiddleware` interrupt.
        3. If yes, render an approval prompt for each pending action and
           resume the graph with the user's decisions.
        4. Repeat until the agent has no more pending interrupts.

    When ``tracer`` is supplied, the turn is bracketed with
    ``turn_start`` / ``turn_end`` events in the JSONL trace log.

    Phase 2 Slice 3: when ``allowlist`` is supplied, ``_collect_decisions``
    auto-approves any HITL action whose tool name is on it (and the user
    can promote a one-off approval to a session-persistent one by picking
    ``approve_always`` at the prompt). ``None`` keeps the legacy "always
    prompt" behavior so existing test entry points stay unaffected.
    """
    run_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    next_input: Any = {"messages": [HumanMessage(content=user_input)]}
    auto_deny = is_read_only(mode)

    if tracer is not None:
        tracer.log("turn_start", thread_id=thread_id, user_input=user_input, mode=mode)

    try:
        while True:
            console.print()
            await _stream_events(console, agent, next_input, run_config, tracer=tracer)
            console.print()

            hitl_request = await _pending_hitl_request(agent, run_config)
            if hitl_request is None:
                return

            decisions = await _collect_decisions(
                console,
                hitl_request,
                auto_deny=auto_deny,
                allowlist=allowlist,
            )
            next_input = Command(resume={"decisions": decisions})
    finally:
        if tracer is not None:
            tracer.log("turn_end", thread_id=thread_id)


async def _stream_events(
    console: Console,
    agent: Any,
    input_payload: Any,
    run_config: RunnableConfig,
    *,
    tracer: TraceLogger | None = None,
) -> None:
    """Pump the agent's event stream into the UI.

    LLM tokens flow through a :class:`StreamRenderer` (markdown-aware via
    Rich ``Live``). Tool calls render separately — ``edit_file`` gets a
    colored unified diff via :func:`render_edit_diff`; other tools use
    the generic header line.

    When ``tracer`` is supplied, ``model_complete`` (with token usage
    when LangChain provides it), ``tool_start``, and ``tool_end`` events
    are recorded.
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
                if tracer is not None:
                    _trace_model_complete(tracer, event)
                continue

            if kind == "on_tool_start":
                renderer.finalize()
                name = event.get("name", "?")
                tool_args = data.get("input", {})
                if tracer is not None:
                    tracer.log("tool_start", tool_name=name, args=tool_args)
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
                output = data.get("output")
                if tracer is not None:
                    tracer.log(
                        "tool_end",
                        tool_name=event.get("name", "?"),
                        output_preview=_preview(output),
                    )
                render_tool_end(console, output)
                continue
    finally:
        renderer.finalize()


_OUTPUT_PREVIEW_LIMIT = 500


def _preview(value: Any) -> str:
    """Render a short, safe preview of a tool's output for the trace log."""
    text = str(value)
    if len(text) > _OUTPUT_PREVIEW_LIMIT:
        return text[:_OUTPUT_PREVIEW_LIMIT] + f"… (+{len(text) - _OUTPUT_PREVIEW_LIMIT} chars)"
    return text


def _trace_model_complete(tracer: TraceLogger, event: dict[str, Any]) -> None:
    """Extract token usage from an ``on_chat_model_end`` event and log it.

    LangChain places token counts on the final message's ``usage_metadata``
    field (``{"input_tokens", "output_tokens", "total_tokens"}``). Some
    providers omit it — we record whatever is available without
    erroring.
    """
    data = event.get("data", {})
    output = data.get("output")
    metadata = event.get("metadata") or {}
    model_name = event.get("name") or metadata.get("ls_model_name")
    fields: dict[str, Any] = {"model": model_name}
    usage = None
    if isinstance(output, AIMessage):
        usage = getattr(output, "usage_metadata", None)
    if isinstance(usage, dict):
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                fields[key] = value
    tracer.log("model_complete", **fields)


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
    allowlist: SessionAllowlist | None = None,
) -> list[dict[str, Any]]:
    """Prompt the user for each ``ActionRequest`` and serialize the decisions.

    Phase 2 Slice 3: when an ``allowlist`` is supplied and the action's
    tool name is already on it, the prompt is skipped and the decision
    auto-resolves to ``approve``. When the user picks ``approve_always``
    at a prompt, the tool name is added to the allowlist so subsequent
    invocations skip the prompt too.

    ``auto_deny`` (``read-only`` mode) always takes precedence over the
    allowlist — a remembered approval doesn't override read-only.
    """
    decisions: list[dict[str, Any]] = []
    for action in hitl_request.get("action_requests", []):
        tool_name = action.get("name", "?")
        if (
            allowlist is not None
            and not auto_deny
            and isinstance(tool_name, str)
            and tool_name in allowlist
        ):
            console.print(
                f"[dim]auto-approved [cyan]{tool_name}[/cyan] (allowlisted this session)[/dim]"
            )
            decisions.append({"type": "approve"})
            continue

        decision = await prompt_approval(
            console,
            tool_name=tool_name,
            tool_args=action.get("args", {}),
            description=action.get("description"),
            auto_deny=auto_deny,
        )
        if (
            decision.type == "approve_always"
            and allowlist is not None
            and isinstance(tool_name, str)
        ):
            allowlist.allow(tool_name)
            console.print(
                f"[green]Will auto-approve[/green] [cyan]{tool_name}[/cyan] "
                f"[green]for the rest of this session.[/green]"
            )
        decisions.append(_decision_payload(decision))
    return decisions


def _decision_payload(decision: ApprovalDecision) -> dict[str, Any]:
    """Convert an :class:`ApprovalDecision` to the HITL resume schema.

    ``approve_always`` is a UX-only signal — DeepAgents only understands
    ``approve`` / ``reject`` / ``edit`` / ``respond``, so we map it back
    to ``approve`` here. The chat loop is responsible for promoting the
    tool name into the :class:`SessionAllowlist` before this conversion.
    """
    payload_type = "approve" if decision.type == "approve_always" else decision.type
    payload: dict[str, Any] = {"type": payload_type}
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
