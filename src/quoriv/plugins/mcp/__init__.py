"""Model Context Protocol (MCP) client.

Allows Quoriv to consume tools and resources from external MCP servers
over stdio or SSE transports.

See https://modelcontextprotocol.io for the protocol specification.

The actual transport work is delegated to ``langchain-mcp-adapters``
(in the ``[mcp]`` install extra); :mod:`quoriv.plugins.mcp.client`
translates Quoriv's TOML config into the connection dict that
adapter library expects.
"""

from __future__ import annotations

from quoriv.plugins.mcp.client import load_mcp_tools

__all__ = ["load_mcp_tools"]
