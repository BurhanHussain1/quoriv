"""Agent core: wraps `deepagents.create_deep_agent` for Quoriv consumers.

This package is the thin layer that sits between Quoriv's UI and the
DeepAgents runtime. It is **not** the agent loop — DeepAgents owns that.

Modules (implemented in later phases):
    agent       Build a configured DeepAgent for a session: wires the chosen
                model, ``LocalShellBackend``, Quoriv-specific tools, permission
                rules translated from the user's mode, memory file paths,
                and a checkpointer.
    routing     Per-task model routing implemented via ``SubAgent`` specs
                (each subagent declares its own ``model=``), not via custom
                middleware.
    events      Subscriber for ``agent.astream_events(version="v2")`` that
                feeds the UI's stream/diff/prompt renderers.

What's **not** here, and why:

    - No runtime/loop module: the compiled LangGraph graph returned by
      ``create_deep_agent`` is the loop.
    - No context-compaction module: ``SummarizationMiddleware`` is built into
      every DeepAgents stack.
    - No tool-invocation plumbing: ``FilesystemMiddleware`` + the plain
      ``tools=`` list cover both built-in and Quoriv-added tools.
"""
