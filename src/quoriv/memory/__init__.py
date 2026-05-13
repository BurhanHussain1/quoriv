"""Persistent memory subsystem.

Four layers, in order of scope:

    Working memory      LangGraph state for the current conversation.
    Session memory      SQLite-backed, resumable across restarts.
    Project memory      PROJECT.md at the repo root, auto-loaded.
    User memory         ~/.quoriv/memory.md, applied across all projects.
"""
