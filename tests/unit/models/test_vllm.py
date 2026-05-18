"""Tests for ``quoriv.models.vllm`` — Phase 3 Slice 4.

vLLM serves an OpenAI-compatible HTTP API, so the provider builds a
``ChatOpenAI`` under the hood pointed at the user's vLLM endpoint.
The test surface differs from the OpenAI provider in a few ways:

  * vLLM **never** raises ``MissingAPIKeyError`` — most local vLLM
    deployments don't enforce auth, so the provider falls through to
    a placeholder when neither env nor keychain has a key.
  * Default ``base_url`` is ``http://localhost:8000/v1`` (vLLM's
    default OpenAI endpoint).
  * Both ``base_url`` and ``api_key`` are overridable via kwargs.
"""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from quoriv.config.keychain import set_api_key
from quoriv.models.base import ModelSpec
from quoriv.models.vllm import _DEFAULT_BASE_URL, _PLACEHOLDER_API_KEY, build

# ---------------------------------------------------------------------------
# Defaults — nothing configured
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_returns_chat_openai(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        # ``fake_keyring`` clears env + keychain. No key, no endpoint
        # configured — the provider must still build cleanly.
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec)
        assert isinstance(model, ChatOpenAI)
        assert getattr(model, "model_name", None) == "my-model"

    def test_default_base_url_used_when_unset(
        self, fake_keyring: dict[tuple[str, str], str]
    ) -> None:
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec)
        # ChatOpenAI exposes the endpoint as ``openai_api_base``
        # (legacy name) — pin to the documented default.
        assert getattr(model, "openai_api_base", None) == _DEFAULT_BASE_URL

    def test_placeholder_api_key_when_none_configured(
        self, fake_keyring: dict[tuple[str, str], str]
    ) -> None:
        # No env, no keychain → placeholder so ChatOpenAI's required
        # api_key field is satisfied. ``api_key`` is stored as a
        # ``SecretStr`` — surface the underlying value for the check.
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec)
        key = model.openai_api_key
        actual = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
        assert actual == _PLACEHOLDER_API_KEY


# ---------------------------------------------------------------------------
# Env-var precedence
# ---------------------------------------------------------------------------


class TestEnvVarPrecedence:
    def test_vllm_base_url_env_var_used(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VLLM_BASE_URL", "http://gpu-box:8000/v1")
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec)
        assert getattr(model, "openai_api_base", None) == "http://gpu-box:8000/v1"

    def test_vllm_api_key_env_var_used(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VLLM_API_KEY", "vllm-env-secret")
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec)
        key = model.openai_api_key
        actual = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
        assert actual == "vllm-env-secret"

    def test_keyring_used_when_no_env(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("VLLM_API_KEY", raising=False)
        set_api_key("vllm", "vllm-keyring-secret")
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec)
        key = model.openai_api_key
        actual = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
        assert actual == "vllm-keyring-secret"


# ---------------------------------------------------------------------------
# Kwarg overrides win
# ---------------------------------------------------------------------------


class TestKwargOverrides:
    def test_base_url_kwarg_beats_env(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Explicit kwarg outranks env var.
        monkeypatch.setenv("VLLM_BASE_URL", "http://from-env:8000/v1")
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec, base_url="http://from-kwarg:8000/v1")
        assert getattr(model, "openai_api_base", None) == "http://from-kwarg:8000/v1"

    def test_api_key_kwarg_beats_env(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VLLM_API_KEY", "from-env")
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec, api_key="from-kwarg")
        key = model.openai_api_key
        actual = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
        assert actual == "from-kwarg"


# ---------------------------------------------------------------------------
# kwargs forwarding for non-default ChatOpenAI params
# ---------------------------------------------------------------------------


class TestKwargsForwarded:
    def test_temperature_forwarded(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        spec = ModelSpec.parse("vllm:my-model")
        model = build(spec, temperature=0.0)
        assert getattr(model, "temperature", None) == pytest.approx(0.0)
