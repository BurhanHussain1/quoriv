"""Approval prompt rendering for HITL interrupts.

When DeepAgents' ``HumanInTheLoopMiddleware`` decides to gate a tool
call, it raises an interrupt with a ``HITLRequest`` payload (see
``langchain.agents.middleware.human_in_the_loop``). This module turns
that into a user-facing prompt:

    1. Render a Rich panel showing the tool name, arguments, and the
       middleware's description.
    2. Ask the user to approve or reject.
    3. In ``read-only`` mode, skip the prompt and auto-reject — the
       agent gets back a clear message explaining the mode.

Phase 5 Slice 2 (v1.2.0): the interactive path used to spin up a
fresh :class:`prompt_toolkit.PromptSession`, which fought with the
chat loop's persistent Application over terminal ownership. The
prompt now runs as a :class:`prompt_toolkit.layout.containers.Float`
modal dialog overlaid on the existing :class:`quoriv.ui.chat_app.ChatApp`,
so the screen never blanks between "agent streaming" and "user
deciding". ``a`` approves, ``r`` rejects, ``A`` approves-and-remembers,
``Esc`` / ``Ctrl+C`` cancel.

Supported decisions: ``approve`` / ``reject`` / ``approve_always``.
``edit`` and ``respond`` (the other two decision types accepted by
the middleware) land in later slices once the UI for editing tool
args exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING, Any, Literal

from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from quoriv.ui.chat_app import ChatApp


DecisionType = Literal["approve", "reject", "approve_always"]
"""Decision kinds the prompt emits.

``approve`` — approve this single call.
``reject`` — deny this call (``message`` carries optional context).
``approve_always`` — approve this call **and** remember the tool for
    the rest of the session (Phase 2 Slice 3). The HITL resume payload
    sent to DeepAgents always uses ``approve``; ``approve_always`` is
    a UX signal that the chat loop should also add the tool to the
    session :class:`quoriv.permissions.SessionAllowlist`.

``edit`` and ``respond`` (the other two decision types accepted by the
middleware) land in later slices once the UI for editing tool args
exists.
"""


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """The user's verdict on a single HITL action request.

    ``message`` is included for ``reject`` decisions so the agent receives
    context (e.g. "denied — read-only mode") instead of a bare error.
    """

    type: DecisionType
    message: str | None = None


READ_ONLY_DENIAL_MESSAGE: str = (
    "Quoriv is running in read-only mode — write and shell tools are denied."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prompt_approval(
    console: Console,
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    description: str | None = None,
    auto_deny: bool = False,
    chat_app: ChatApp | None = None,
) -> ApprovalDecision:
    """Render an approval panel and return the user's decision.

    Args:
        console: Rich console for output. When ``chat_app`` is wired
            this is typically ``chat_app.console`` — every panel ends
            up in the persistent Application's scrollback.
        tool_name: The proposed tool (e.g. ``"edit_file"``).
        tool_args: The tool call's arguments.
        description: Optional human-readable description from the
            middleware. When present, it's surfaced inside the modal
            body.
        auto_deny: If ``True``, render the panel but skip the
            interactive prompt and return a ``reject`` decision
            immediately. Used for ``read-only`` mode.
        chat_app: The persistent :class:`ChatApp` to overlay the modal
            on. When ``None`` (legacy + headless tests), the function
            renders the panel and short-circuits to a ``reject`` —
            interactive approval requires a live Application.

    Returns:
        :class:`ApprovalDecision` describing what the user chose.
    """
    _render_approval_panel(console, tool_name, tool_args, description)

    if auto_deny:
        console.print("[yellow]Auto-denied (read-only mode).[/yellow]")
        return ApprovalDecision(type="reject", message=READ_ONLY_DENIAL_MESSAGE)

    if chat_app is None:
        # No live Application — the legacy ``PromptSession`` path is
        # gone (it fought with the persistent app over the terminal).
        # Calls without a ``chat_app`` are typically tests stubbing
        # the function; reject so a misconfigured production call
        # surfaces visibly instead of hanging.
        console.print(
            "[red]No interactive UI available — auto-rejecting approval.[/red]"
        )
        return ApprovalDecision(
            type="reject",
            message="No interactive UI available for approval.",
        )

    body_text = _render_approval_body_ansi(tool_name, tool_args, description)
    choice = await chat_app.prompt_approval_modal(body_text=body_text)
    if choice == "approve":
        return ApprovalDecision(type="approve")
    if choice == "approve_always":
        return ApprovalDecision(type="approve_always")
    return ApprovalDecision(type="reject", message="User rejected this tool call.")


def parse_choice(raw: str) -> DecisionType | None:
    """Parse a raw input string into a decision type, or ``None`` if invalid.

    Accepted aliases:
        approve:        a, approve, y, yes
        approve_always: A, always, aa  (capital A is the only single-letter
                        form that distinguishes from "approve once" — kept
                        case-sensitive on purpose so a lowercase "a" never
                        accidentally promotes the tool)
        reject:         r, reject, n, no, deny

    Note: this function preserves case for the ``A`` short form. Every
    other alias is matched case-insensitively. Retained for any caller
    or test that wants to translate a textual hint into a decision
    type without going through the modal.
    """
    stripped = raw.strip()
    if stripped in {"A", "aa"} or stripped.lower() == "always":
        return "approve_always"
    norm = stripped.lower()
    if norm in {"a", "approve", "y", "yes"}:
        return "approve"
    if norm in {"r", "reject", "n", "no", "deny"}:
        return "reject"
    return None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _render_approval_panel(
    console: Console,
    tool_name: str,
    tool_args: dict[str, Any],
    description: str | None,
) -> None:
    """Render the panel that frames the approval prompt (scrollback copy).

    The modal also embeds a copy of this content for visibility while
    focus is on the dialog; printing here keeps the panel in
    scrollback so users see *what was asked* even after the modal
    closes.
    """
    args_pretty = _format_args(tool_args)
    body_lines = [
        f"[bold cyan]{tool_name}[/bold cyan]",
        "",
        "[dim]args:[/dim]",
        args_pretty,
    ]
    if description:
        body_lines.extend(["", "[dim]description:[/dim]", description])
    body = "\n".join(body_lines)
    console.print(
        Panel(
            body,
            title="[yellow]approval required[/yellow]",
            border_style="yellow",
            expand=False,
        )
    )


def _render_approval_body_ansi(
    tool_name: str,
    tool_args: dict[str, Any],
    description: str | None,
) -> str:
    """Render the modal body as ANSI text via Rich.

    The Dialog widget accepts ANSI-formatted text, so we let Rich do
    the heavy lifting (panel border, syntax colours) and hand the
    resulting bytes to prompt_toolkit. A fresh ``Console`` is used
    rather than the chat console because the latter is wired to the
    Application's scrollback — printing the modal body through it
    would echo the panel into scrollback a second time.
    """
    buf = StringIO()
    console = Console(
        file=buf,
        force_terminal=True,
        color_system="truecolor",
        width=80,
        soft_wrap=False,
    )
    args_pretty = _format_args(tool_args)
    body_lines = [
        f"[bold cyan]{tool_name}[/bold cyan]",
        "",
        "[dim]args:[/dim]",
        args_pretty,
    ]
    if description:
        body_lines.extend(["", "[dim]description:[/dim]", description])
    console.print(
        Panel(
            "\n".join(body_lines),
            title="[yellow]approval required[/yellow]",
            border_style="yellow",
            expand=False,
        )
    )
    return buf.getvalue()


def _format_args(args: dict[str, Any], *, indent: int = 2) -> str:
    """Pretty-print tool args as JSON when possible."""
    try:
        return json.dumps(args, indent=indent, default=str)
    except (TypeError, ValueError):
        return repr(args)
