"""Tests for `quoriv.config.keychain`."""

from __future__ import annotations

import pytest

from quoriv.config.keychain import (
    PROVIDER_ENV_VARS,
    SERVICE_NAME,
    delete_api_key,
    get_api_key,
    list_known_providers,
    set_api_key,
)

# ---------------------------------------------------------------------------
# set / get / delete round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_set_then_get(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        set_api_key("openai", "sk-test-12345")
        assert get_api_key("openai") == "sk-test-12345"
        assert fake_keyring == {(SERVICE_NAME, "openai"): "sk-test-12345"}

    def test_get_missing_returns_none(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        assert get_api_key("openai") is None

    def test_set_overwrites(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        set_api_key("openai", "old-key")
        set_api_key("openai", "new-key")
        assert get_api_key("openai") == "new-key"

    def test_delete_existing_returns_true(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        set_api_key("openai", "sk-test")
        assert delete_api_key("openai") is True
        assert get_api_key("openai") is None

    def test_delete_missing_returns_false(self, fake_keyring: dict[tuple[str, str], str]) -> None:
        assert delete_api_key("openai") is False


# ---------------------------------------------------------------------------
# Environment variable precedence
# ---------------------------------------------------------------------------


class TestEnvVarPrecedence:
    def test_env_var_wins_over_keyring(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_api_key("openai", "from-keyring")
        monkeypatch.setenv("OPENAI_API_KEY", "from-env")
        assert get_api_key("openai") == "from-env"

    def test_falls_back_to_keyring_when_env_unset(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_api_key("openai", "from-keyring")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert get_api_key("openai") == "from-keyring"

    def test_empty_env_var_treated_as_unset(
        self,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        set_api_key("openai", "from-keyring")
        monkeypatch.setenv("OPENAI_API_KEY", "")
        # Empty string is falsy, so keyring should be consulted next.
        assert get_api_key("openai") == "from-keyring"

    def test_unknown_provider_with_no_env_returns_keyring_value(
        self, fake_keyring: dict[tuple[str, str], str]
    ) -> None:
        # A provider not in PROVIDER_ENV_VARS still works through keyring.
        set_api_key("mystery-provider", "abc")
        assert get_api_key("mystery-provider") == "abc"


# ---------------------------------------------------------------------------
# list_known_providers
# ---------------------------------------------------------------------------


class TestListKnownProviders:
    def test_includes_openai(self) -> None:
        assert "openai" in list_known_providers()

    def test_returns_sorted(self) -> None:
        providers = list_known_providers()
        assert providers == sorted(providers)

    def test_matches_provider_env_vars_keys(self) -> None:
        assert set(list_known_providers()) == set(PROVIDER_ENV_VARS.keys())
