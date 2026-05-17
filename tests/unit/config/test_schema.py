"""Tests for `quoriv.config.schema`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quoriv.config.schema import (
    CostConfig,
    CostRate,
    ModelConfig,
    PermissionsConfig,
    PluginsConfig,
    QuorivConfig,
    ToolsConfig,
    UIConfig,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_empty_input_uses_all_defaults(self) -> None:
        config = QuorivConfig.model_validate({})
        assert config.model.default == "openai:gpt-4.1"
        assert config.model.fast == "openai:gpt-4o-mini"
        assert config.model.strong == "openai:gpt-4.1"
        assert config.permissions.mode == "ask"
        assert config.ui.theme == "dark"
        assert config.tools.disabled == []

    def test_each_section_constructible_without_args(self) -> None:
        ModelConfig()
        PermissionsConfig()
        UIConfig()
        ToolsConfig()
        QuorivConfig()


# ---------------------------------------------------------------------------
# Permission mode validation
# ---------------------------------------------------------------------------


class TestPermissionMode:
    @pytest.mark.parametrize("mode", ["read-only", "ask", "auto", "yolo"])
    def test_valid_modes_accepted(self, mode: str) -> None:
        config = PermissionsConfig.model_validate({"mode": mode})
        assert config.mode == mode

    @pytest.mark.parametrize("mode", ["readonly", "ASK", "off", ""])
    def test_invalid_modes_rejected(self, mode: str) -> None:
        with pytest.raises(ValidationError):
            PermissionsConfig.model_validate({"mode": mode})


# ---------------------------------------------------------------------------
# Theme validation
# ---------------------------------------------------------------------------


class TestTheme:
    @pytest.mark.parametrize("theme", ["dark", "light", "auto"])
    def test_valid_themes_accepted(self, theme: str) -> None:
        config = UIConfig.model_validate({"theme": theme})
        assert config.theme == theme

    def test_invalid_theme_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UIConfig.model_validate({"theme": "monokai"})


# ---------------------------------------------------------------------------
# Strictness (extra fields)
# ---------------------------------------------------------------------------


class TestExtraFieldsRejected:
    def test_unknown_top_level_section(self) -> None:
        with pytest.raises(ValidationError):
            QuorivConfig.model_validate({"unknown_section": {}})

    def test_unknown_model_field(self) -> None:
        with pytest.raises(ValidationError):
            ModelConfig.model_validate({"default": "openai:x", "bogus": "y"})

    def test_unknown_permissions_field(self) -> None:
        with pytest.raises(ValidationError):
            PermissionsConfig.model_validate({"mode": "ask", "extra": True})


# ---------------------------------------------------------------------------
# Partial overrides
# ---------------------------------------------------------------------------


class TestPartialOverride:
    def test_setting_only_permissions_keeps_other_defaults(self) -> None:
        config = QuorivConfig.model_validate({"permissions": {"mode": "auto"}})
        assert config.permissions.mode == "auto"
        assert config.model.default == "openai:gpt-4.1"
        assert config.ui.theme == "dark"

    def test_setting_only_one_model_field(self) -> None:
        config = QuorivConfig.model_validate({"model": {"fast": "openai:gpt-4o-mini-2024-07-18"}})
        assert config.model.fast == "openai:gpt-4o-mini-2024-07-18"
        assert config.model.default == "openai:gpt-4.1"


# ---------------------------------------------------------------------------
# Tools section
# ---------------------------------------------------------------------------


class TestToolsConfig:
    def test_disabled_list_accepted(self) -> None:
        config = ToolsConfig.model_validate({"disabled": ["web_search", "execute"]})
        assert config.disabled == ["web_search", "execute"]

    def test_disabled_defaults_to_empty(self) -> None:
        assert ToolsConfig().disabled == []


# ---------------------------------------------------------------------------
# CostConfig — Slice 9d
# ---------------------------------------------------------------------------


class TestCostConfig:
    def test_defaults_to_empty_rates(self) -> None:
        assert CostConfig().rates == {}

    def test_quoriv_config_exposes_cost_section(self) -> None:
        config = QuorivConfig.model_validate({})
        assert config.cost.rates == {}

    def test_rate_accepts_zero(self) -> None:
        # Local-only providers (Ollama, vLLM) ship as 0.0/0.0 in the
        # built-in table; user overrides must accept the same.
        rate = CostRate.model_validate({"input_per_1k": 0.0, "output_per_1k": 0.0})
        assert rate.input_per_1k == 0.0
        assert rate.output_per_1k == 0.0

    def test_rate_rejects_negative_input(self) -> None:
        with pytest.raises(ValidationError):
            CostRate.model_validate({"input_per_1k": -0.001, "output_per_1k": 0.01})

    def test_rate_rejects_negative_output(self) -> None:
        with pytest.raises(ValidationError):
            CostRate.model_validate({"input_per_1k": 0.01, "output_per_1k": -0.001})

    def test_rate_requires_both_fields(self) -> None:
        with pytest.raises(ValidationError):
            CostRate.model_validate({"input_per_1k": 0.01})
        with pytest.raises(ValidationError):
            CostRate.model_validate({"output_per_1k": 0.01})

    def test_rate_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            CostRate.model_validate(
                {"input_per_1k": 0.01, "output_per_1k": 0.02, "currency": "USD"}
            )

    def test_cost_section_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            CostConfig.model_validate({"rates": {}, "currency": "USD"})

    def test_rates_map_round_trip(self) -> None:
        config = QuorivConfig.model_validate(
            {
                "cost": {
                    "rates": {
                        "openai:gpt-4o": {"input_per_1k": 0.0030, "output_per_1k": 0.0120},
                        "ollama:": {"input_per_1k": 0.0, "output_per_1k": 0.0},
                    }
                }
            }
        )
        assert config.cost.rates["openai:gpt-4o"].input_per_1k == 0.0030
        assert config.cost.rates["openai:gpt-4o"].output_per_1k == 0.0120
        assert config.cost.rates["ollama:"].input_per_1k == 0.0


# ---------------------------------------------------------------------------
# PluginsConfig — Phase 2 Slice 5
# ---------------------------------------------------------------------------


class TestPluginsConfig:
    def test_defaults_to_empty_disabled_list(self) -> None:
        assert PluginsConfig().disabled == []

    def test_quoriv_config_exposes_plugins_section(self) -> None:
        config = QuorivConfig.model_validate({})
        assert config.plugins.disabled == []

    def test_disabled_list_accepted(self) -> None:
        config = PluginsConfig.model_validate({"disabled": ["noisy_plugin", "slow_one"]})
        assert config.disabled == ["noisy_plugin", "slow_one"]

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PluginsConfig.model_validate({"disabled": [], "extras": "nope"})

    def test_quoriv_config_round_trip_with_plugins(self) -> None:
        config = QuorivConfig.model_validate({"plugins": {"disabled": ["heavy_metal"]}})
        assert config.plugins.disabled == ["heavy_metal"]
