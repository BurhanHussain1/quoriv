"""Quoriv-specific tools, layered on top of DeepAgents' built-ins.

DeepAgents already provides the standard file and shell tools through
``FilesystemMiddleware`` and ``SandboxBackendProtocol``:

    ls, read_file, write_file, edit_file, glob, grep,    (built into DeepAgents)
    execute, task, write_todos                            (built into DeepAgents)

This package contains the tools DeepAgents does **not** ship — registered as
plain callables and passed to ``create_deep_agent`` via ``tools=[...]``.

Modules:
    ast_tools   Slice 4 ships a Python-only ``find_symbol``. Slice 4b adds
                tree-sitter-based ``go_to_definition`` / ``find_references``
                for ~30 languages.
    git         Slice 5 ships read-only ``git_status`` / ``git_diff`` /
                ``git_log`` / ``git_blame``. Slice 5b adds
                ``git_add`` / ``git_commit`` / ``git_stash``, gated by HITL
                via :data:`quoriv.permissions.GIT_WRITE_TOOLS`.
    tests       (Slice 6) Language-aware test runner.
    web         (Phase 3) web_search and web_fetch.

What's **not** here, and why:

    - No ``files.py`` / ``read``/``write``/``edit`` — DeepAgents owns these.
    - No ``search.py`` / ``grep`` — DeepAgents owns this (literal substring;
      add a ``regex_grep`` tool here if regex is needed later).
    - No ``shell.py`` / ``execute`` — ``LocalShellBackend`` owns this.
    - No ``patch.py`` — use DeepAgents' ``edit_file``.
    - No ``base.py`` — use ``langchain_core.tools.tool`` decorator directly.
"""

from __future__ import annotations

from quoriv.tools.ast_tools import find_symbol
from quoriv.tools.git import (
    git_add,
    git_blame,
    git_commit,
    git_diff,
    git_log,
    git_stash,
    git_status,
)

QUORIV_TOOLS = [
    find_symbol,
    git_status,
    git_diff,
    git_log,
    git_blame,
    git_add,
    git_commit,
    git_stash,
]
"""Default Quoriv-specific tools handed to ``create_deep_agent(tools=...)``."""

__all__ = [
    "QUORIV_TOOLS",
    "find_symbol",
    "git_add",
    "git_blame",
    "git_commit",
    "git_diff",
    "git_log",
    "git_stash",
    "git_status",
]
