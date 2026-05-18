"""Tests for the MCP schema in ``quoriv.config.schema`` — Phase 2 Slice 6."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quoriv.config.schema import MCPConfig, MCPServerConfig, QuorivConfig

# ---------------------------------------------------------------------------
# MCPServerConfig — transport discriminator + per-transport validation
# ---------------------------------------------------------------------------


class TestMCPServerConfigStdio:
    def test_minimal_stdio(self) -> None:
        spec = MCPServerConfig.model_validate({"transport": "stdio", "command": "uvx"})
        assert spec.transport == "stdio"
        assert spec.command == "uvx"
        assert spec.args == []

    def test_stdio_with_args_and_env(self) -> None:
        spec = MCPServerConfig.model_validate(
            {
                "transport": "stdio",
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "env": {"USER_AGENT": "quoriv/0.0.1"},
            }
        )
        assert spec.args == ["mcp-server-fetch"]
        assert spec.env == {"USER_AGENT": "quoriv/0.0.1"}

    def test_default_transport_is_stdio(self) -> None:
        # Most servers are stdio in practice — default to that so a
        # ``[mcp.servers.foo] command = "..."`` snippet works without
        # repeating ``transport = "stdio"``.
        spec = MCPServerConfig.model_validate({"command": "uvx"})
        assert spec.transport == "stdio"

    def test_stdio_without_command_rejected(self) -> None:
        with pytest.raises(ValidationError, match="stdio transport requires 'command'"):
            MCPServerConfig.model_validate({"transport": "stdio"})

    def test_stdio_with_url_rejected(self) -> None:
        # Cross-transport field — clearly a user error, fail loudly.
        with pytest.raises(ValidationError, match="forbids 'url' / 'headers'"):
            MCPServerConfig.model_validate(
                {"transport": "stdio", "command": "uvx", "url": "http://x"}
            )


class TestMCPServerConfigSse:
    def test_minimal_sse(self) -> None:
        spec = MCPServerConfig.model_validate(
            {"transport": "sse", "url": "https://mcp.example.com"}
        )
        assert spec.transport == "sse"
        assert spec.url == "https://mcp.example.com"
        assert spec.headers is None

    def test_sse_with_headers(self) -> None:
        spec = MCPServerConfig.model_validate(
            {
                "transport": "sse",
                "url": "https://mcp.example.com",
                "headers": {"Authorization": "Bearer xxx"},
            }
        )
        assert spec.headers == {"Authorization": "Bearer xxx"}

    def test_sse_without_url_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sse transport requires 'url'"):
            MCPServerConfig.model_validate({"transport": "sse"})

    def test_sse_with_command_rejected(self) -> None:
        with pytest.raises(ValidationError, match="forbids 'command'"):
            MCPServerConfig.model_validate(
                {"transport": "sse", "url": "https://x", "command": "uvx"}
            )


# ---------------------------------------------------------------------------
# MCPServerConfig — strictness
# ---------------------------------------------------------------------------


class TestMCPServerConfigStrict:
    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MCPServerConfig.model_validate(
                {"transport": "stdio", "command": "uvx", "made_up": True}
            )

    def test_unknown_transport_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MCPServerConfig.model_validate({"transport": "carrier-pigeon", "url": "http://x"})


# ---------------------------------------------------------------------------
# MCPConfig + integration with QuorivConfig
# ---------------------------------------------------------------------------


class TestMCPConfig:
    def test_defaults_to_empty_servers(self) -> None:
        assert MCPConfig().servers == {}

    def test_quoriv_config_exposes_mcp_section(self) -> None:
        assert QuorivConfig.model_validate({}).mcp.servers == {}

    def test_servers_map_round_trips(self) -> None:
        config = QuorivConfig.model_validate(
            {
                "mcp": {
                    "servers": {
                        "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
                        "github": {
                            "transport": "sse",
                            "url": "https://mcp.github.example",
                        },
                    }
                }
            }
        )
        assert set(config.mcp.servers) == {"fetch", "github"}
        assert config.mcp.servers["fetch"].command == "uvx"
        assert config.mcp.servers["github"].url == "https://mcp.github.example"

    def test_mcp_section_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            MCPConfig.model_validate({"servers": {}, "global_timeout": 30})
