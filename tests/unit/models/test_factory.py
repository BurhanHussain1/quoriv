"""Tests for `quoriv.models.factory`."""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from quoriv.models.factory import (
    UnknownProviderError,
    get_model,
    list_providers,
)

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


class TestListProviders:
    def test_openai_registered_in_phase_1(self) -> None:
        assert "openai" in list_providers()

    def test_results_sorted(self) -> None:
        providers = list_providers()
        assert providers == sorted(providers)


# ---------------------------------------------------------------------------
# get_model: error paths (no API key needed to reach these)
# ---------------------------------------------------------------------------


class TestGetModelErrors:
    def test_unknown_provider_raises(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        with pytest.raises(UnknownProviderError) as exc_info:
            get_model("notreal:whatever")
        assert exc_info.value.provider == "notreal"
        assert "openai" in exc_info.value.known

    def test_malformed_identifier_raises_value_error(
        self, fake_keyring: dict[tuple[str, str], str]
    ) -> None:
        with pytest.raises(ValueError):
            get_model("no-colon-here")


# ---------------------------------------------------------------------------
# get_model: success path with OpenAI
# ---------------------------------------------------------------------------


class TestGetModelOpenAI:
    def test_returns_chat_openai_instance(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
        model = get_model("openai:gpt-4o-mini")
        assert isinstance(model, ChatOpenAI)

    def test_model_name_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
        model = get_model("openai:gpt-4.1")
        # ChatOpenAI exposes the model name on `.model_name` in current
        # langchain-openai versions.
        assert "gpt-4.1" in getattr(model, "model_name", "") or "gpt-4.1" in str(model)

    def test_kwargs_forwarded(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
        model = get_model("openai:gpt-4o-mini", temperature=0.123)
        # ChatOpenAI stores temperature as a pydantic field.
        assert getattr(model, "temperature", None) == pytest.approx(0.123)
