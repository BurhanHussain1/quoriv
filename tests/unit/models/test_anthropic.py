"""Tests for ``quoriv.models.anthropic`` — Phase 3 Slice 1.

Mirrors :mod:`tests.unit.models.test_openai`: each provider is a thin
adapter, so they share the same shape — missing-key handling, env-var
key resolution, keychain fallback, and kwargs forwarding to the
underlying LangChain model.
"""

from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic

from quoriv.config.keychain import set_api_key
from quoriv.models.anthropic import build
from quoriv.models.base import MissingAPIKeyError, ModelSpec

# ---------------------------------------------------------------------------
# Missing key handling
# ---------------------------------------------------------------------------


class TestMissingKey:
    def test_raises_when_no_key_anywhere(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        spec = ModelSpec.parse("anthropic:claude-sonnet-4-6")
        with pytest.raises(MissingAPIKeyError) as exc_info:
            build(spec)
        assert exc_info.value.provider == "anthropic"
        assert exc_info.value.env_var == "ANTHROPIC_API_KEY"


# ---------------------------------------------------------------------------
# Successful construction
# ---------------------------------------------------------------------------


class TestBuildFromEnv:
    def test_uses_env_var_key(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-test")
        spec = ModelSpec.parse("anthropic:claude-sonnet-4-6")
        model = build(spec)
        assert isinstance(model, ChatAnthropic)
        # The parsed name (after the first colon) is the model
        # identifier Anthropic sees.
        assert getattr(model, "model", None) == "claude-sonnet-4-6"


class TestBuildFromKeyring:
    def test_uses_keyring_when_no_env(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        set_api_key("anthropic", "sk-ant-keyring-test")
        spec = ModelSpec.parse("anthropic:claude-sonnet-4-6")
        model = build(spec)
        assert isinstance(model, ChatAnthropic)


# ---------------------------------------------------------------------------
# Identifier parsing — Anthropic model names can carry dashes/numbers
# ---------------------------------------------------------------------------


class TestIdentifierShapes:
    def test_opus_model_id_parses_through(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        # Modern Anthropic ids carry version dashes; make sure they
        # flow through ``ModelSpec.parse`` unchanged.
        spec = ModelSpec.parse("anthropic:claude-opus-4-7")
        assert spec.provider == "anthropic"
        assert spec.name == "claude-opus-4-7"
        model = build(spec)
        assert getattr(model, "model", None) == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# kwargs forwarding
# ---------------------------------------------------------------------------


class TestKwargsForwarded:
    def test_temperature_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        spec = ModelSpec.parse("anthropic:claude-sonnet-4-6")
        model = build(spec, temperature=0.0)
        assert getattr(model, "temperature", None) == pytest.approx(0.0)

    def test_max_tokens_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        spec = ModelSpec.parse("anthropic:claude-sonnet-4-6")
        model = build(spec, max_tokens=128)
        # Stored as either max_tokens or max_tokens_to_sample depending
        # on the langchain-anthropic version.
        actual = getattr(model, "max_tokens", None) or getattr(model, "max_tokens_to_sample", None)
        assert actual == 128
