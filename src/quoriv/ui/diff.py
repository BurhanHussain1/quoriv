"""Diff rendering for proposed file edits.

When the agent calls ``edit_file``, its arguments include the old and new
strings. Rather than dumping the raw args, we compute a unified diff and
render it with syntax highlighting so the user can read the change at a
glance.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from rich.syntax import Syntax

if TYPE_CHECKING:
    from rich.console import Console


def compute_diff(
    old_string: str,
    new_string: str,
    *,
    file_path: str = "",
    context_lines: int = 3,
) -> str:
    """Return a unified-diff string for an ``edit_file`` proposal.

    Returns the empty string when ``old_string == new_string`` — the
    caller decides how to render "no changes".
    """
    diff_iter = difflib.unified_diff(
        old_string.splitlines(keepends=True),
        new_string.splitlines(keepends=True),
        fromfile=f"a{file_path}",
        tofile=f"b{file_path}",
        n=context_lines,
    )
    return "".join(diff_iter)


def render_edit_diff(
    console: Console,
    *,
    file_path: str,
    old_string: str,
    new_string: str,
    context_lines: int = 3,
) -> None:
    """Render a colored unified diff for a proposed ``edit_file`` call."""
    diff_text = compute_diff(
        old_string,
        new_string,
        file_path=file_path,
        context_lines=context_lines,
    )

    label = file_path or "(unknown path)"
    if not diff_text.strip():
        console.print(f"\n[dim cyan]→ edit_file[/dim cyan]  [dim]{label} — no changes[/dim]")
        return

    console.print(f"\n[dim cyan]→ edit_file[/dim cyan]  [dim]{label}[/dim]")
    console.print(
        Syntax(
            diff_text,
            "diff",
            theme="ansi_dark",
            word_wrap=False,
            line_numbers=False,
        )
    )
