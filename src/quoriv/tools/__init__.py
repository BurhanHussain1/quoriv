"""Quoriv-specific tools, layered on top of DeepAgents' built-ins.

DeepAgents already provides the standard file and shell tools through
``FilesystemMiddleware`` and ``SandboxBackendProtocol``:

    ls, read_file, write_file, edit_file, glob, grep,    (built into DeepAgents)
    execute, task, write_todos                            (built into DeepAgents)

This package contains the tools DeepAgents does **not** ship — registered as
plain callables and passed to ``create_deep_agent`` via ``tools=[...]``.

Modules:
    ast_tools   Slice 4 shipped a Python-only ``find_symbol``. Slice 4b
                expanded it to multi-language via tree-sitter (Python /
                JS / TS / Go / Rust / Java / C / C++ / C# / Ruby / PHP /
                ...) and added ``go_to_definition`` + ``find_references``.
    git         Slice 5 ships read-only ``git_status`` / ``git_diff`` /
                ``git_log`` / ``git_blame``. Slice 5b adds
                ``git_add`` / ``git_commit`` / ``git_stash``, gated by HITL
                via :data:`quoriv.permissions.GIT_WRITE_TOOLS`.
    tests       Slice 6 ships ``run_tests`` — auto-detects pytest / npm /
                cargo / go from marker files and runs the suite, returning
                structured pass/fail metadata.
    web         Phase 3 Slice 6 ships ``web_fetch`` for HTTP-based
                page retrieval; Slice 7 adds ``web_search`` backed
                by Tavily (requires the ``[search]`` install extra).

What's **not** here, and why:

    - No ``files.py`` / ``read``/``write``/``edit`` — DeepAgents owns these.
    - No ``search.py`` / ``grep`` — DeepAgents owns this (literal substring;
      add a ``regex_grep`` tool here if regex is needed later).
    - No ``shell.py`` / ``execute`` — ``LocalShellBackend`` owns this.
    - No ``patch.py`` — use DeepAgents' ``edit_file``.
    - No ``base.py`` — use ``langchain_core.tools.tool`` decorator directly.
"""

from __future__ import annotations

from quoriv.tools.ast_tools import find_references, find_symbol, go_to_definition
from quoriv.tools.git import (
    git_add,
    git_blame,
    git_commit,
    git_diff,
    git_log,
    git_stash,
    git_status,
)
from quoriv.tools.tests import run_tests
from quoriv.tools.web import web_fetch, web_search

QUORIV_TOOLS = [
    find_symbol,
    go_to_definition,
    find_references,
    git_status,
    git_diff,
    git_log,
    git_blame,
    git_add,
    git_commit,
    git_stash,
    run_tests,
    web_fetch,
    web_search,
]
"""Default Quoriv-specific tools handed to ``create_deep_agent(tools=...)``."""

__all__ = [
    "QUORIV_TOOLS",
    "find_references",
    "find_symbol",
    "git_add",
    "git_blame",
    "git_commit",
    "git_diff",
    "git_log",
    "git_stash",
    "git_status",
    "go_to_definition",
    "run_tests",
    "web_fetch",
    "web_search",
]
