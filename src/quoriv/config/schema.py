"""Pydantic v2 schemas for Quoriv configuration.

These models define the shape of every section in `config.toml`, validate
incoming data, supply defaults for unset fields, and reject unknown keys
to catch typos early.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

PermissionMode = Literal["read-only", "ask", "auto", "yolo"]
"""Permission posture for tool execution.

    read-only   Reads allowed, all writes/shell blocked.
    ask         Prompt before every write or shell call (default).
    auto        Auto-run safe tools; prompt for risky ones.
    yolo        Run everything without prompts. Use with care.
"""

Theme = Literal["dark", "light", "auto"]
"""Terminal color theme. `auto` detects from the terminal."""


# ---------------------------------------------------------------------------
# Section schemas
# ---------------------------------------------------------------------------


class ModelConfig(BaseModel):
    """LLM model selection and per-task routing.

    Model identifiers are `"provider:name"` strings, e.g. ``"openai:gpt-4.1"``
    or ``"ollama:qwen2.5-coder:32b"``. See `quoriv.models.factory` for the
    set of supported providers.
    """

    model_config = ConfigDict(extra="forbid")

    default: str = Field(
        default="openai:gpt-4.1",
        description="Default model unless overridden by `--model` or routing.",
    )
    fast: str = Field(
        default="openai:gpt-4o-mini",
        description="Cheap/fast model for trivial calls (routing, summaries).",
    )
    strong: str = Field(
        default="openai:gpt-4.1",
        description="Strong model for hard reasoning (planning, coding).",
    )
    fallbacks: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of 'provider:model' identifiers to try when "
            "the primary model raises a transient error (rate limit, "
            "5xx, network failure). LangChain's RunnableWithFallbacks "
            "walks the list in order and surfaces the first response "
            "that lands. Empty list (the default) disables fallbacks."
        ),
    )


class PermissionsConfig(BaseModel):
    """Permission system configuration."""

    model_config = ConfigDict(extra="forbid")

    mode: PermissionMode = Field(
        default="ask",
        description="Default permission posture for new sessions.",
    )


class UIConfig(BaseModel):
    """Terminal UI preferences."""

    model_config = ConfigDict(extra="forbid")

    theme: Theme = Field(default="dark", description="Color theme.")


class ToolsConfig(BaseModel):
    """Built-in tool enable/disable configuration."""

    model_config = ConfigDict(extra="forbid")

    disabled: list[str] = Field(
        default_factory=list,
        description="Tool names to disable (e.g. 'web_search', 'execute').",
    )


class CostRate(BaseModel):
    """USD price per 1,000 tokens for one ``provider:model`` prefix.

    Same shape as :class:`quoriv.observability.cost.ProviderRate` but as
    a pydantic model so user-supplied values pass through TOML → schema
    validation (non-negative floats) before reaching the rate table.
    """

    model_config = ConfigDict(extra="forbid")

    input_per_1k: float = Field(
        ...,
        ge=0.0,
        description="USD per 1,000 input tokens.",
    )
    output_per_1k: float = Field(
        ...,
        ge=0.0,
        description="USD per 1,000 output tokens.",
    )


class CostConfig(BaseModel):
    """User-supplied overrides for the ``/cost`` rate table.

    Keys are ``provider:model`` prefixes matched by longest-prefix lookup
    against the merged table — same rule as the built-in
    :data:`quoriv.observability.cost.RATES`. A user entry with the same
    key as a built-in shadows the built-in; an entry with a more
    specific prefix wins via longest-match.
    """

    model_config = ConfigDict(extra="forbid")

    rates: dict[str, CostRate] = Field(
        default_factory=dict,
        description="Map of 'provider:model' prefix to CostRate.",
    )


class SubAgentRoleConfig(BaseModel):
    """Per-role override for a built-in subagent — Phase 2 Slice 4.

    Each role (researcher / debugger / reviewer) is wired by
    :mod:`quoriv.core.subagents` with sensible defaults; this section
    lets users redirect a role to a different model without rewriting
    the underlying spec.

    ``model`` accepts:

        * ``"default"`` (the default value) — use
          :attr:`ModelConfig.default`. Same model the main agent runs.
        * ``"fast"`` — use :attr:`ModelConfig.fast`. Right for the
          researcher when token cost matters more than depth.
        * ``"strong"`` — use :attr:`ModelConfig.strong`. Right for the
          debugger and reviewer when hard reasoning matters.
        * Any ``"provider:name"`` literal — bypasses the lookup and
          uses the named model directly.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default="default",
        description=(
            "Model token: 'default' / 'fast' / 'strong' / "
            "'provider:name'. Resolved at build_agent() time."
        ),
    )


class MCPServerConfig(BaseModel):
    """One MCP (Model Context Protocol) server connection — Phase 2 Slice 6.

    Two transports are supported, distinguished by ``transport``:

        ``stdio``   Launch the server as a subprocess and talk over
                    its stdin/stdout. ``command`` is required;
                    ``args``/``env`` are optional.
        ``sse``     Connect to a long-lived HTTP/SSE endpoint.
                    ``url`` is required; ``headers`` is optional.

    Fields outside the active transport are ignored at runtime but
    rejected at validation time (``extra="forbid"``) so a typo in the
    server config fails loudly.
    """

    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio", "sse"] = Field(
        default="stdio",
        description="Transport for the MCP server connection.",
    )
    command: str | None = Field(
        default=None,
        description="Executable to launch (stdio transport only).",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command-line arguments for the stdio executable.",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Environment variables to set for the stdio subprocess.",
    )
    url: str | None = Field(
        default=None,
        description="HTTP(S) endpoint URL (sse transport only).",
    )
    headers: dict[str, str] | None = Field(
        default=None,
        description="Headers to send on the SSE connection (e.g. auth tokens).",
    )

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> Self:
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio transport requires 'command'")
            if self.url is not None or self.headers is not None:
                raise ValueError("stdio transport forbids 'url' / 'headers' — those are sse-only")
        elif self.transport == "sse":
            if not self.url:
                raise ValueError("sse transport requires 'url'")
            if self.command is not None or self.args or self.env is not None:
                raise ValueError(
                    "sse transport forbids 'command' / 'args' / 'env' — those are stdio-only"
                )
        return self


class MCPConfig(BaseModel):
    """MCP server registry — Phase 2 Slice 6.

    Keys are user-supplied server names; values are
    :class:`MCPServerConfig`. The agent loads tools from every
    registered server at session start and merges them into the
    main ``tools=`` list. Tool names are kept distinct using each
    server's name as a prefix (handled by
    ``langchain-mcp-adapters``).
    """

    model_config = ConfigDict(extra="forbid")

    servers: dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="Map of server-name to MCPServerConfig.",
    )


class PluginsConfig(BaseModel):
    """Third-party plugin enable/disable — Phase 2 Slice 5.

    Plugins register tools via the ``quoriv.plugins`` setuptools
    entry-point group. The loader (:mod:`quoriv.plugins.loader`)
    discovers them at session start and merges the returned tools
    into the agent's ``tools=`` list.

    ``disabled`` lets a user opt a specific plugin out without
    uninstalling the package — useful when a noisy plugin is
    interfering with the current workflow.
    """

    model_config = ConfigDict(extra="forbid")

    disabled: list[str] = Field(
        default_factory=list,
        description=(
            "Names of plugins to skip. Match the entry-point name "
            "registered under the 'quoriv.plugins' group."
        ),
    )


class SubAgentsConfig(BaseModel):
    """Built-in subagent roles — researcher / debugger / reviewer.

    The agent delegates to these via DeepAgents' ``task`` tool. Each
    role ships with a fixed system prompt (see
    :mod:`quoriv.core.subagents`); this section only routes which
    model handles which role.
    """

    model_config = ConfigDict(extra="forbid")

    researcher: SubAgentRoleConfig = Field(
        default_factory=lambda: SubAgentRoleConfig(model="fast"),
        description="Read-only exploration / discovery subagent.",
    )
    debugger: SubAgentRoleConfig = Field(
        default_factory=lambda: SubAgentRoleConfig(model="strong"),
        description="Deep-reasoning subagent for hard bug investigation.",
    )
    reviewer: SubAgentRoleConfig = Field(
        default_factory=lambda: SubAgentRoleConfig(model="strong"),
        description="Read-only critique subagent — surfaces issues in proposed changes.",
    )


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class QuorivConfig(BaseModel):
    """Top-level Quoriv configuration.

    Merged from (in order of increasing precedence):
        1. Built-in defaults declared on each section.
        2. ~/.quoriv/config.toml (global).
        3. <repo>/.quoriv/config.toml (project).
    """

    model_config = ConfigDict(extra="forbid")

    model: ModelConfig = Field(default_factory=ModelConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    subagents: SubAgentsConfig = Field(default_factory=SubAgentsConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
