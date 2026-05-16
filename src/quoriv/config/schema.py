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
