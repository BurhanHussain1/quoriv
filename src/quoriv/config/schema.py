"""Pydantic v2 schemas for Quoriv configuration.

These models define the shape of every section in `config.toml`, validate
incoming data, supply defaults for unset fields, and reject unknown keys
to catch typos early.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
