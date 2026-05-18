"""MCP (Model Context Protocol) client — Phase 2 Slice 6.

Connects to external MCP servers configured via the
``[mcp.servers.NAME]`` blocks in ``config.toml`` and surfaces their
tools as LangChain ``BaseTool`` instances. The discovered tools are
merged into the main agent's ``tools=`` list at session start.

Two transports are supported (matching ``langchain-mcp-adapters``):

    ``stdio``   The server is launched as a subprocess; we talk to
                it over stdin/stdout.
    ``sse``     The server is reached over an HTTP/SSE endpoint.

The actual wire work is delegated to
``langchain_mcp_adapters.client.MultiServerMCPClient``. This module
is a thin Quoriv-specific adapter: it translates
:class:`quoriv.config.schema.MCPServerConfig` into the connection
dict that adapter library expects, then calls ``get_tools()`` and
returns the result.

The adapter library is in the ``[mcp]`` install extra. If it's not
installed (or any other unrecoverable error happens at import time),
:func:`load_mcp_tools` logs a warning and returns an empty list
rather than failing the chat session — same defensive pattern as
:mod:`quoriv.plugins.loader`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from loguru import logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from quoriv.config.schema import MCPServerConfig


def _connection_dict(spec: MCPServerConfig) -> dict[str, Any]:
    """Translate one :class:`MCPServerConfig` into a connection dict.

    The shape matches the ``StdioConnection`` / ``SSEConnection``
    ``TypedDict``\\s in
    ``langchain_mcp_adapters.sessions``. Fields irrelevant to the
    chosen transport are omitted (the validator on
    :class:`MCPServerConfig` already rejected them at config-load
    time, so this is just a defensive pass).
    """
    if spec.transport == "stdio":
        # ``command`` is guaranteed non-None by the schema validator.
        out: dict[str, Any] = {
            "transport": "stdio",
            "command": spec.command,
            "args": list(spec.args),
        }
        if spec.env is not None:
            out["env"] = dict(spec.env)
        return out
    # sse — ``url`` is guaranteed non-None by the schema validator.
    out = {"transport": "sse", "url": spec.url}
    if spec.headers is not None:
        out["headers"] = dict(spec.headers)
    return out


async def load_mcp_tools(
    servers: dict[str, MCPServerConfig],
) -> list[BaseTool]:
    """Connect to every configured MCP server and return their tools.

    Args:
        servers: Map of server-name to
            :class:`quoriv.config.schema.MCPServerConfig`. Typically
            ``config.mcp.servers`` from a loaded :class:`QuorivConfig`.

    Returns:
        Flat list of LangChain tools across all servers. Tool names
        are made distinct by the adapter library when needed.
        Returns ``[]`` if ``servers`` is empty, the adapter library
        is unavailable, or every server failed to connect — each
        failure is logged but does not raise.
    """
    if not servers:
        return []

    # Defensive import: the adapter library lives in the [mcp]
    # install extra. A user without the extra installed still gets
    # a working chat session — just without MCP tools.
    try:
        from langchain_mcp_adapters.client import (  # noqa: PLC0415  (intentional lazy import)
            MultiServerMCPClient,
        )
    except ImportError as exc:
        logger.warning(
            "MCP servers configured but `langchain-mcp-adapters` not installed "
            "({}); skipping. Install Quoriv with the [mcp] extra to enable.",
            exc,
        )
        return []

    connections = {name: _connection_dict(spec) for name, spec in servers.items()}
    try:
        # ``MultiServerMCPClient`` types ``connections`` as a union of
        # ``StdioConnection`` / ``SSEConnection`` / … TypedDicts. Our
        # dict literals carry the same shape but the type system can't
        # narrow from a plain dict — cast away.
        client = MultiServerMCPClient(connections=cast("dict[str, Any]", connections))
    except Exception as exc:  # client construction shouldn't fail, but guard anyway
        logger.warning("MultiServerMCPClient init failed ({}); skipping MCP.", exc)
        return []

    try:
        tools = await client.get_tools()
    except Exception as exc:
        logger.warning(
            "MCP tool discovery failed ({}); session continues without MCP tools.",
            exc,
        )
        return []
    return list(tools)
