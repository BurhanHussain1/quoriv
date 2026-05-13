"""Agent core: DeepAgents wiring, runtime loop, model routing, context.

This package contains the parts of Quoriv that are independent of any
specific client (CLI, VSCode extension, web UI). It can be imported and
driven by any consumer.

Modules (implemented in Phase 1):
    agent      DeepAgents wiring and tool injection.
    runtime    The main agent loop and streaming event production.
    routing    Per-task model routing (small vs strong model).
    context    Context window management and compaction.
    events     Event bus that consumers subscribe to.
"""
