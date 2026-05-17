"""Approval prompt rendering for HITL interrupts.

When DeepAgents' ``HumanInTheLoopMiddleware`` decides to gate a tool
call, it raises an interrupt with a ``HITLRequest`` payload (see
``langchain.agents.middleware.human_in_the_loop``). This module turns
that into a user-facing prompt:

    1. Render a Rich panel showing the tool name, arguments, and the
       middleware's description.
    2. Ask the user to approve or reject.
    3. In ``read-only`` mode, skip the prompt and auto-reject — the agent
       gets back a clear message explaining the mode.

Phase 1 Slice 2 supports ``approve`` and ``reject``. ``edit`` and
``respond`` (the other two decision types accepted by the middleware)
land in later slices once the UI for editing tool args exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.panel import Panel

if TYPE_CHECKING:
    from rich.console import Console


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
) -> ApprovalDecision:
    """Render an approval panel and return the user's decision.

    Args:
        console: Rich console for output.
        tool_name: The proposed tool (e.g. ``"edit_file"``).
        tool_args: The tool call's arguments.
        description: Optional human-readable description from the
            middleware. When present, it replaces the auto-generated
            "Tool: ... Args: ..." line.
        auto_deny: If ``True``, render the panel but skip the interactive
            prompt and return a ``reject`` decision immediately. Used for
            ``read-only`` mode.

    Returns:
        :class:`ApprovalDecision` describing what the user chose.
    """
    _render_approval_panel(console, tool_name, tool_args, description)

    if auto_deny:
        console.print("[yellow]Auto-denied (read-only mode).[/yellow]")
        return ApprovalDecision(type="reject", message=READ_ONLY_DENIAL_MESSAGE)

    session: PromptSession[str] = PromptSession()
    while True:
        raw = await session.prompt_async(
            HTML(
                "<ansigreen>approve</ansigreen> / "
                "<ansired>reject</ansired> / "
                "<ansiyellow>always</ansiyellow>  [a/r/A] > "
            )
        )
        choice = parse_choice(raw)
        if choice == "approve":
            return ApprovalDecision(type="approve")
        if choice == "approve_always":
            return ApprovalDecision(type="approve_always")
        if choice == "reject":
            return ApprovalDecision(type="reject", message="User rejected this tool call.")
        console.print(
            "[dim]Please answer 'a' (approve), 'r' (reject), or 'A' / 'always' "
            "(approve and remember for this session). Aliases: y/yes/n/no.[/dim]"
        )


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
    other alias is matched case-insensitively.
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
    """Render the panel that frames the approval prompt."""
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


def _format_args(args: dict[str, Any], *, indent: int = 2) -> str:
    """Pretty-print tool args as JSON when possible."""
    try:
        return json.dumps(args, indent=indent, default=str)
    except (TypeError, ValueError):
        return repr(args)
