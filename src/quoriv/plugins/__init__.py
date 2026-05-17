"""Plugin system.

Two complementary extension mechanisms:

    Python plugin API     Third-party packages register tools, sub-agents,
                          and slash commands via entry points (Phase 2
                          Slice 5 — see :mod:`quoriv.plugins.loader`).

    MCP client            Connect to external Model Context Protocol
                          servers (GitHub, Slack, databases, etc.).
"""

from __future__ import annotations

from quoriv.plugins.loader import (
    QUORIV_PLUGINS_GROUP,
    PluginRecord,
    discover_plugin_tools,
    list_plugins,
)

__all__ = [
    "QUORIV_PLUGINS_GROUP",
    "PluginRecord",
    "discover_plugin_tools",
    "list_plugins",
]
