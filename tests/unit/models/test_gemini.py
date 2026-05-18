"""Tests for ``quoriv.models.gemini`` — Phase 3 Slice 3.

Mirrors :mod:`tests.unit.models.test_anthropic` since the cloud
providers share the same shape: missing-key handling, env-var key
resolution, keychain fallback, and kwargs forwarding. The
gemini-specific quirk: the API key kwarg is ``google_api_key``, not
``api_key`` — that's the LangChain wrapper's choice.
"""

from __future__ import annotations

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI

from quoriv.config.keychain import set_api_key
from quoriv.models.base import MissingAPIKeyError, ModelSpec
from quoriv.models.gemini import build

# ---------------------------------------------------------------------------
# Missing key handling
# ---------------------------------------------------------------------------


class TestMissingKey:
    def test_raises_when_no_key_anywhere(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        spec = ModelSpec.parse("gemini:gemini-1.5-flash")
        with pytest.raises(MissingAPIKeyError) as exc_info:
            build(spec)
        assert exc_info.value.provider == "gemini"
        # The keychain map points both "gemini" and "google" at the
        # same env var; the provider raises with that name.
        assert exc_info.value.env_var == "GOOGLE_API_KEY"


# ---------------------------------------------------------------------------
# Successful construction
# ---------------------------------------------------------------------------


class TestBuildFromEnv:
    def test_uses_env_var_key(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-env-test")
        spec = ModelSpec.parse("gemini:gemini-1.5-flash")
        model = build(spec)
        assert isinstance(model, ChatGoogleGenerativeAI)
        assert getattr(model, "model", None) == "gemini-1.5-flash"

    def test_pro_model_id_parses_through(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
        spec = ModelSpec.parse("gemini:gemini-1.5-pro")
        assert spec.provider == "gemini"
        assert spec.name == "gemini-1.5-pro"
        model = build(spec)
        assert getattr(model, "model", None) == "gemini-1.5-pro"


class TestBuildFromKeyring:
    def test_uses_keyring_when_no_env(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        set_api_key("gemini", "AIza-keyring-test")
        spec = ModelSpec.parse("gemini:gemini-1.5-flash")
        model = build(spec)
        assert isinstance(model, ChatGoogleGenerativeAI)


# ---------------------------------------------------------------------------
# kwargs forwarding
# ---------------------------------------------------------------------------


class TestKwargsForwarded:
    def test_temperature_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
        spec = ModelSpec.parse("gemini:gemini-1.5-flash")
        model = build(spec, temperature=0.0)
        assert getattr(model, "temperature", None) == pytest.approx(0.0)

    def test_max_output_tokens_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
        spec = ModelSpec.parse("gemini:gemini-1.5-flash")
        model = build(spec, max_output_tokens=128)
        # Stored as max_output_tokens by the LangChain wrapper.
        assert getattr(model, "max_output_tokens", None) == 128
