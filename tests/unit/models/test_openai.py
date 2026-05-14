"""Tests for `quoriv.models.openai`."""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from quoriv.config.keychain import set_api_key
from quoriv.models.base import MissingAPIKeyError, ModelSpec
from quoriv.models.openai import build

# ---------------------------------------------------------------------------
# Missing key handling
# ---------------------------------------------------------------------------


class TestMissingKey:
    def test_raises_when_no_key_anywhere(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        spec = ModelSpec.parse("openai:gpt-4o-mini")
        with pytest.raises(MissingAPIKeyError) as exc_info:
            build(spec)
        assert exc_info.value.provider == "openai"
        assert exc_info.value.env_var == "OPENAI_API_KEY"


# ---------------------------------------------------------------------------
# Successful construction
# ---------------------------------------------------------------------------


class TestBuildFromEnv:
    def test_uses_env_var_key(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")
        spec = ModelSpec.parse("openai:gpt-4o-mini")
        model = build(spec)
        assert isinstance(model, ChatOpenAI)


class TestBuildFromKeyring:
    def test_uses_keyring_when_no_env(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        set_api_key("openai", "sk-keyring-test")
        spec = ModelSpec.parse("openai:gpt-4o-mini")
        model = build(spec)
        assert isinstance(model, ChatOpenAI)


# ---------------------------------------------------------------------------
# kwargs forwarding
# ---------------------------------------------------------------------------


class TestKwargsForwarded:
    def test_temperature_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        spec = ModelSpec.parse("openai:gpt-4o-mini")
        model = build(spec, temperature=0.0)
        assert getattr(model, "temperature", None) == pytest.approx(0.0)

    def test_max_tokens_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        spec = ModelSpec.parse("openai:gpt-4o-mini")
        model = build(spec, max_tokens=128)
        # max_tokens may be stored as max_tokens or max_completion_tokens
        # depending on langchain-openai version.
        actual = getattr(model, "max_tokens", None) or getattr(model, "max_completion_tokens", None)
        assert actual == 128
