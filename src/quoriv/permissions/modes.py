"""Translate Quoriv's user-facing permission modes to DeepAgents config.

Quoriv exposes four modes:

    read-only   Investigation only. Writes/shell still prompt at the agent
                level, but the approval UI auto-denies every one.
    ask         Default. Prompt before every write or shell call.
    auto        Auto-run safe tools (writes); prompt only for shell.
    yolo        No prompts. Use with care.

This module's job is to compile a mode label into the two underlying
DeepAgents mechanisms:

    interrupt_on={...}   pauses the agent before listed tool calls
                         (enforced by HumanInTheLoopMiddleware)
    permissions=[...]    rejects tool calls at the FilesystemMiddleware
                         layer (NOT yet wired — DeepAgents 0.6.1
                         incompatibility with sandbox backends)

For Phase 1 Slice 1 we only emit ``interrupt_on``. Hard write blocking
for ``read-only`` is handled at the approval UI (Slice 2) by auto-denying
any pause.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from langchain.agents.middleware import InterruptOnConfig

PermissionMode = Literal["read-only", "ask", "auto", "yolo"]


WRITE_TOOLS: Final[frozenset[str]] = frozenset({"write_file", "edit_file"})
"""Names of DeepAgents tools that mutate the filesystem.

These are the tools we gate behind ``interrupt_on`` in modes ``ask`` and
``read-only``. Note that DeepAgents emits these names from
``FilesystemMiddleware`` — if those names change upstream, update here.
"""


SHELL_TOOLS: Final[frozenset[str]] = frozenset({"execute"})
"""Names of DeepAgents tools that execute shell commands.

Gated in every mode except ``yolo``.
"""


def interrupt_on_for_mode(mode: PermissionMode) -> dict[str, bool | InterruptOnConfig]:
    """Compile a mode label to DeepAgents' ``interrupt_on=`` dict.

    Returns:
        A mapping ``{tool_name: True}`` for every tool that should pause
        the agent for human approval before running. Empty dict means no
        prompts. The return type is wider than what this function currently
        produces (it always returns ``bool`` values) — later slices may
        return :class:`langchain.agents.middleware.InterruptOnConfig`
        values for richer prompt metadata.

    Examples:
        >>> interrupt_on_for_mode("yolo")
        {}
        >>> sorted(interrupt_on_for_mode("auto"))
        ['execute']
        >>> sorted(interrupt_on_for_mode("ask"))
        ['edit_file', 'execute', 'write_file']
    """
    if mode == "yolo":
        return {}
    if mode == "auto":
        return dict.fromkeys(SHELL_TOOLS, True)
    # read-only and ask: prompt before every write and shell call.
    return dict.fromkeys(WRITE_TOOLS | SHELL_TOOLS, True)


def is_read_only(mode: PermissionMode) -> bool:
    """Whether the mode means "deny every write/shell call at the prompt"."""
    return mode == "read-only"
