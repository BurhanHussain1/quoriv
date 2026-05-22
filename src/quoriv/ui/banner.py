"""Welcome banner rendering — Phase 5 Slice 1 (UI polish).

The chat session boots with a Rich Panel showing project identity,
the resolved session context (model / mode / cwd / loaded memory
files), and a compact grid of available slash commands. Replaces the
plain text block we shipped through v1.0.

Pure-render module — no I/O, no side effects beyond ``console.print``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.align import Align
from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from quoriv import __version__

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console, ConsoleRenderable


# ASCII logo. Kept narrow (≤ 60 cols) so it renders cleanly in
# split-pane terminals and on 80-col SSH sessions.
_LOGO = r"""
   ___                  _
  / _ \ _   _  ___ _ __(_)_   __
 | | | | | | |/ _ \ '__| \ \ / /
 | |_| | |_| |  __/ |  | |\ V /
  \__\_\\__,_|\___|_|  |_| \_/
"""


def _slash_command_grid(slash_commands: dict[str, str]) -> Columns:
    """Render the slash command list as a two-column grid.

    Each entry is ``/name — description``, dim-styled for the
    description so the command tokens pop. Columns auto-balance so a
    narrow terminal collapses to one column.
    """
    items: list[Text] = []
    for name, desc in slash_commands.items():
        text = Text()
        text.append(name, style="bold cyan")
        text.append("  ")
        text.append(desc, style="dim")
        items.append(text)
    return Columns(items, equal=False, expand=True, column_first=True)


def render_welcome_banner(
    console: Console,
    *,
    model_id: str,
    mode: str,
    cwd: Path | None,
    memory_files: list[Path] | None = None,
    slash_commands: dict[str, str] | None = None,
) -> None:
    """Print the session-start banner.

    Args:
        console: The session's Rich console.
        model_id: Provider:name string the agent will use.
        mode: Permission mode label (`read-only` / `ask` / `auto` / `yolo`).
        cwd: Working directory the agent is rooted in.
        memory_files: Memory files DeepAgents loaded (``PROJECT.md`` etc.).
            Omitted from the banner when empty so first-time users
            without a project memory file don't see a stray "Memory:" row.
        slash_commands: Mapping of ``/name → description``. When
            supplied, rendered as a two-column grid at the bottom of
            the banner. ``None`` hides the grid entirely (useful for
            tests that only want the identity panel).
    """
    cwd_display = str(cwd) if cwd is not None else "(current directory)"

    # Top: ASCII logo + tagline, centered.
    logo = Text(_LOGO, style="bold magenta")
    tagline = Text(
        f"v{__version__} — open-source terminal AI coding agent",
        style="dim italic",
    )
    header = Group(Align.center(logo), Align.center(tagline))

    # Middle: a compact key/value table for the session context.
    context = Table.grid(padding=(0, 2))
    context.add_column(style="bold", justify="right")
    context.add_column()
    context.add_row("Model", f"[cyan]{model_id}[/cyan]")
    context.add_row("Mode", f"[cyan]{mode}[/cyan]")
    context.add_row("Root", f"[cyan]{cwd_display}[/cyan]")
    if memory_files:
        names = ", ".join(p.name for p in memory_files)
        context.add_row("Memory", f"[cyan]{names}[/cyan]")

    pieces: list[ConsoleRenderable] = [header, Text(), Align.center(context)]

    # Bottom: slash command grid, if supplied.
    if slash_commands:
        pieces.append(Text())
        pieces.append(Text("Slash commands", style="bold underline"))
        pieces.append(_slash_command_grid(slash_commands))

    pieces.append(Text())
    pieces.append(
        Text.from_markup(
            "Type [bold yellow]/help[/bold yellow] for commands  •  "
            "[bold yellow]/exit[/bold yellow] to quit",
            justify="center",
        )
    )

    console.print(Panel(Group(*pieces), border_style="magenta", padding=(1, 2)))
