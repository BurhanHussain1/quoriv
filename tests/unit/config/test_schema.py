"""Tests for `quoriv.config.schema`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quoriv.config.schema import (
    ModelConfig,
    PermissionsConfig,
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
