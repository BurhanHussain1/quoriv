"""Tests for ``quoriv.plugins.mcp.client`` — Phase 2 Slice 6.

The actual transport work goes through
``langchain_mcp_adapters.client.MultiServerMCPClient``. We
monkeypatch that class to keep the test suite hermetic — no real
MCP servers spawned, no network connections opened.
"""

from __future__ import annotations

import builtins
from typing import Any

import pytest

from quoriv.config.schema import MCPServerConfig
from quoriv.plugins.mcp.client import _connection_dict, load_mcp_tools

# ---------------------------------------------------------------------------
# _connection_dict — pure translation, no I/O
# ---------------------------------------------------------------------------


class TestConnectionDict:
    def test_stdio_minimal(self) -> None:
        spec = MCPServerConfig.model_validate({"command": "uvx"})
        assert _connection_dict(spec) == {
            "transport": "stdio",
            "command": "uvx",
            "args": [],
        }

    def test_stdio_includes_env_when_set(self) -> None:
        spec = MCPServerConfig.model_validate({"command": "uvx", "env": {"X": "1"}})
        assert _connection_dict(spec)["env"] == {"X": "1"}

    def test_stdio_omits_env_when_none(self) -> None:
        # ``MultiServerMCPClient`` treats missing keys as "don't set"
        # while ``env=None`` could be ambiguous — be explicit.
        spec = MCPServerConfig.model_validate({"command": "uvx"})
        assert "env" not in _connection_dict(spec)

    def test_sse_minimal(self) -> None:
        spec = MCPServerConfig.model_validate(
            {"transport": "sse", "url": "https://mcp.example.com"}
        )
        assert _connection_dict(spec) == {
            "transport": "sse",
            "url": "https://mcp.example.com",
        }

    def test_sse_includes_headers_when_set(self) -> None:
        spec = MCPServerConfig.model_validate(
            {
                "transport": "sse",
                "url": "https://mcp.example.com",
                "headers": {"Authorization": "Bearer xxx"},
            }
        )
        assert _connection_dict(spec)["headers"] == {"Authorization": "Bearer xxx"}


# ---------------------------------------------------------------------------
# load_mcp_tools — empty + defensive paths
# ---------------------------------------------------------------------------


class TestLoadMcpToolsEdgeCases:
    async def test_empty_servers_returns_empty(self) -> None:
        # Fast path — no client construction, no import overhead.
        assert await load_mcp_tools({}) == []

    async def test_missing_adapter_lib_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Simulate the ``[mcp]`` extra not being installed by making
        # the lazy import inside ``load_mcp_tools`` raise. ``__import__``
        # is the lowest-level hook a ``from x import y`` statement
        # actually calls, so patching it here works even when the
        # runtime has cached the module elsewhere.
        real_builtin = builtins.__import__

        def fake_builtin_import(
            name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: Any = (),
            level: int = 0,
        ) -> Any:
            if name.startswith("langchain_mcp_adapters"):
                raise ImportError("simulated missing adapter")
            return real_builtin(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_builtin_import)

        servers = {"x": MCPServerConfig.model_validate({"command": "uvx"})}
        assert await load_mcp_tools(servers) == []


# ---------------------------------------------------------------------------
# load_mcp_tools — happy path with stubbed MultiServerMCPClient
# ---------------------------------------------------------------------------


class _FakeTool:
    """Stand-in for a LangChain BaseTool the adapter would emit."""

    def __init__(self, name: str) -> None:
        self.name = name


class _FakeClient:
    """Captures connections + returns canned tools."""

    last_instance: _FakeClient | None = None

    def __init__(self, connections: dict[str, Any]) -> None:
        self.connections = connections
        _FakeClient.last_instance = self

    async def get_tools(self) -> list[Any]:
        # One tool per registered server, named after the server.
        return [_FakeTool(f"{name}__tool") for name in self.connections]


class TestLoadMcpToolsHappyPath:
    async def test_passes_translated_connections_to_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", _FakeClient)
        servers = {
            "fetch": MCPServerConfig.model_validate(
                {"command": "uvx", "args": ["mcp-server-fetch"]}
            ),
            "github": MCPServerConfig.model_validate(
                {"transport": "sse", "url": "https://gh.example"}
            ),
        }
        await load_mcp_tools(servers)
        assert _FakeClient.last_instance is not None
        connections = _FakeClient.last_instance.connections
        assert set(connections) == {"fetch", "github"}
        assert connections["fetch"]["transport"] == "stdio"
        assert connections["fetch"]["command"] == "uvx"
        assert connections["fetch"]["args"] == ["mcp-server-fetch"]
        assert connections["github"]["transport"] == "sse"
        assert connections["github"]["url"] == "https://gh.example"

    async def test_returns_tools_from_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", _FakeClient)
        servers = {
            "a": MCPServerConfig.model_validate({"command": "x"}),
            "b": MCPServerConfig.model_validate({"command": "y"}),
        }
        tools = await load_mcp_tools(servers)
        assert {t.name for t in tools} == {"a__tool", "b__tool"}


# ---------------------------------------------------------------------------
# load_mcp_tools — failure handling
# ---------------------------------------------------------------------------


class TestLoadMcpToolsFailures:
    async def test_client_init_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BoomClient:
            def __init__(self, connections: dict[str, Any]) -> None:
                raise RuntimeError("simulated init failure")

        monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", _BoomClient)
        servers = {"x": MCPServerConfig.model_validate({"command": "uvx"})}
        assert await load_mcp_tools(servers) == []

    async def test_get_tools_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _GetToolsBoom:
            def __init__(self, connections: dict[str, Any]) -> None:
                self.connections = connections

            async def get_tools(self) -> list[Any]:
                raise RuntimeError("server unreachable")

        monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", _GetToolsBoom)
        servers = {"x": MCPServerConfig.model_validate({"command": "uvx"})}
        # No exception leaks; session continues with no MCP tools.
        assert await load_mcp_tools(servers) == []
