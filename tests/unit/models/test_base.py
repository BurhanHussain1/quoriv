"""Tests for `quoriv.models.base`."""

from __future__ import annotations

import pytest

from quoriv.models.base import (
    MissingAPIKeyError,
    ModelCapabilities,
    ModelSpec,
)

# ---------------------------------------------------------------------------
# ModelSpec.parse
# ---------------------------------------------------------------------------


class TestModelSpecParse:
    def test_simple_identifier(self) -> None:
        spec = ModelSpec.parse("openai:gpt-4.1")
        assert spec.provider == "openai"
        assert spec.name == "gpt-4.1"

    def test_name_containing_colon_splits_only_first(self) -> None:
        # Ollama tags use a colon: 'qwen2.5-coder:32b'.
        spec = ModelSpec.parse("ollama:qwen2.5-coder:32b")
        assert spec.provider == "ollama"
        assert spec.name == "qwen2.5-coder:32b"

    def test_anthropic_dotted_name(self) -> None:
        spec = ModelSpec.parse("anthropic:claude-sonnet-4-6")
        assert spec.provider == "anthropic"
        assert spec.name == "claude-sonnet-4-6"

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "openai",
            ":gpt-4.1",
            "openai:",
            ":",
        ],
    )
    def test_invalid_identifier_raises(self, bad: str) -> None:
        with pytest.raises(ValueError):
            ModelSpec.parse(bad)


# ---------------------------------------------------------------------------
# ModelSpec round-trip
# ---------------------------------------------------------------------------


class TestModelSpecStr:
    def test_str_round_trip(self) -> None:
        original = "openai:gpt-4o-mini"
        spec = ModelSpec.parse(original)
        assert str(spec) == original

    def test_str_round_trip_with_colon_in_name(self) -> None:
        original = "ollama:qwen2.5-coder:32b"
        spec = ModelSpec.parse(original)
        assert str(spec) == original


# ---------------------------------------------------------------------------
# ModelCapabilities defaults
# ---------------------------------------------------------------------------


class TestModelCapabilities:
    def test_defaults(self) -> None:
        caps = ModelCapabilities()
        assert caps.supports_streaming is True
        assert caps.supports_tools is True
        assert caps.supports_vision is False
        assert caps.context_window is None

    def test_explicit_construction(self) -> None:
        caps = ModelCapabilities(
            supports_streaming=False,
            supports_tools=True,
            supports_vision=True,
            context_window=128_000,
        )
        assert caps.supports_streaming is False
        assert caps.supports_vision is True
        assert caps.context_window == 128_000


# ---------------------------------------------------------------------------
# MissingAPIKeyError
# ---------------------------------------------------------------------------


class TestMissingAPIKeyError:
    def test_message_includes_provider_and_env_var(self) -> None:
        err = MissingAPIKeyError("openai", "OPENAI_API_KEY")
        message = str(err)
        assert "openai" in message
        assert "OPENAI_API_KEY" in message

    def test_attributes_preserved(self) -> None:
        err = MissingAPIKeyError("openai", "OPENAI_API_KEY")
        assert err.provider == "openai"
        assert err.env_var == "OPENAI_API_KEY"
