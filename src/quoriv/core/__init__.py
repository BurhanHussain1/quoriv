"""Agent core: wraps `deepagents.create_deep_agent` for Quoriv consumers.

This package is the thin layer that sits between Quoriv's UI and the
DeepAgents runtime. It is **not** the agent loop — DeepAgents owns that.

Modules:
    agent       Build a configured DeepAgent for a session: wires the chosen
                model, ``LocalShellBackend``, permission mode → ``interrupt_on``,
                Quoriv-specific tools, and a checkpointer (defaults to
                :class:`AsyncSqliteSaver`).
    events      Rich-rendering helpers for ``agent.astream_events(version="v2")``
                output: render_token, render_tool_start, render_tool_end.
    persistence Slice 7 — DB-path helpers and the :class:`SessionRegistry`
                sidecar mapping user names to ``thread_id`` values.
    routing     (Phase 2) Per-task model routing implemented via ``SubAgent``
                specs (each subagent declares its own ``model=``), not via
                custom middleware.

Note: ``PATH_PROTECTION`` lives in :mod:`quoriv.permissions.paths` — the
canonical location for permission/path policy.

What's **not** here, and why:

    - No runtime/loop module: the compiled LangGraph graph returned by
      ``create_deep_agent`` is the loop.
    - No context-compaction module: ``SummarizationMiddleware`` is built into
      every DeepAgents stack.
    - No tool-invocation plumbing: ``FilesystemMiddleware`` + the plain
      ``tools=`` list cover both built-in and Quoriv-added tools.
"""

from __future__ import annotations

from quoriv.core.agent import build_agent
from quoriv.core.events import render_token, render_tool_end, render_tool_start
from quoriv.core.memory import (
    MemoryCandidate,
    memory_candidates,
    resolve_memory_files,
)
from quoriv.core.persistence import (
    NamedSession,
    SessionRegistry,
    db_path,
    ensure_quoriv_dir,
    quoriv_dir,
    registry_path,
    trace_path,
    traces_dir,
)

__all__ = [
    "MemoryCandidate",
    "NamedSession",
    "SessionRegistry",
    "build_agent",
    "db_path",
    "ensure_quoriv_dir",
    "memory_candidates",
    "quoriv_dir",
    "registry_path",
    "render_token",
    "render_tool_end",
    "render_tool_start",
    "resolve_memory_files",
    "trace_path",
    "traces_dir",
]
