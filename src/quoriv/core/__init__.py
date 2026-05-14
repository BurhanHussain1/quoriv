"""Agent core: wraps `deepagents.create_deep_agent` for Quoriv consumers.

This package is the thin layer that sits between Quoriv's UI and the
DeepAgents runtime. It is **not** the agent loop — DeepAgents owns that.

Modules:
    agent       Build a configured DeepAgent for a session: wires the chosen
                model, ``LocalShellBackend``, permission mode → ``interrupt_on``,
                and a checkpointer. Later Phase 1 slices extend with
                Quoriv-specific tools, ``SqliteSaver`` checkpointing, and
                memory file loading.
    events      Rich-rendering helpers for ``agent.astream_events(version="v2")``
                output: render_token, render_tool_start, render_tool_end.
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

__all__ = [
    "build_agent",
    "render_token",
    "render_tool_end",
    "render_tool_start",
]
