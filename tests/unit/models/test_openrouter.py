"""Tests for ``quoriv.models.openrouter`` — Phase 3 Slice 5.

OpenRouter is OpenAI-compatible, so the provider builds a
``ChatOpenAI`` pointed at the OpenRouter cloud endpoint. Differs from
the vLLM provider in two ways:

  * The API key **is** required — OpenRouter is a paid service.
  * The default ``base_url`` is OpenRouter's fixed cloud endpoint,
    not a localhost guess.

The model-name half of the identifier carries a ``/`` (vendor/model)
which ``ModelSpec.parse`` preserves because it splits on the first
colon only.
"""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from quoriv.config.keychain import set_api_key
from quoriv.models.base import MissingAPIKeyError, ModelSpec
from quoriv.models.openrouter import _OPENROUTER_BASE_URL, build

# ---------------------------------------------------------------------------
# Missing key handling
# ---------------------------------------------------------------------------


class TestMissingKey:
    def test_raises_when_no_key_anywhere(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        spec = ModelSpec.parse("openrouter:anthropic/claude-3.5-sonnet")
        with pytest.raises(MissingAPIKeyError) as exc_info:
            build(spec)
        assert exc_info.value.provider == "openrouter"
        assert exc_info.value.env_var == "OPENROUTER_API_KEY"


# ---------------------------------------------------------------------------
# Successful construction
# ---------------------------------------------------------------------------


class TestBuildFromEnv:
    def test_uses_env_var_key(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env-test")
        spec = ModelSpec.parse("openrouter:anthropic/claude-3.5-sonnet")
        model = build(spec)
        assert isinstance(model, ChatOpenAI)
        # Model name carries the vendor/model slash through to ChatOpenAI.
        assert getattr(model, "model_name", None) == "anthropic/claude-3.5-sonnet"

    def test_default_base_url_points_at_openrouter(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        spec = ModelSpec.parse("openrouter:anthropic/claude-3.5-sonnet")
        model = build(spec)
        assert getattr(model, "openai_api_base", None) == _OPENROUTER_BASE_URL


class TestBuildFromKeyring:
    def test_uses_keyring_when_no_env(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        set_api_key("openrouter", "sk-or-keyring-test")
        spec = ModelSpec.parse("openrouter:anthropic/claude-3.5-sonnet")
        model = build(spec)
        assert isinstance(model, ChatOpenAI)


# ---------------------------------------------------------------------------
# Identifier shapes — vendor/model slashes must round-trip
# ---------------------------------------------------------------------------


class TestIdentifierShapes:
    def test_slash_in_model_name_preserved(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        spec = ModelSpec.parse("openrouter:meta-llama/llama-3.1-405b-instruct")
        assert spec.provider == "openrouter"
        assert spec.name == "meta-llama/llama-3.1-405b-instruct"
        model = build(spec)
        assert getattr(model, "model_name", None) == "meta-llama/llama-3.1-405b-instruct"


# ---------------------------------------------------------------------------
# Kwarg overrides
# ---------------------------------------------------------------------------


class TestKwargOverrides:
    def test_base_url_kwarg_overrides_default(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Rare but supported — point at an OpenRouter proxy or
        # staging endpoint.
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        spec = ModelSpec.parse("openrouter:anthropic/claude-3.5-sonnet")
        model = build(spec, base_url="https://openrouter-staging.example/v1")
        assert getattr(model, "openai_api_base", None) == ("https://openrouter-staging.example/v1")

    def test_temperature_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        spec = ModelSpec.parse("openrouter:anthropic/claude-3.5-sonnet")
        model = build(spec, temperature=0.0)
        assert getattr(model, "temperature", None) == pytest.approx(0.0)
