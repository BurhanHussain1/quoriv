"""Tests for ``quoriv.providers`` — Phase 5 Slice 4 onboarding registry."""

from __future__ import annotations

from quoriv.providers import (
    PROVIDERS,
    ProviderEntry,
    get_provider,
    model_choices,
    provider_choices,
)


class TestProviderRegistry:
    def test_provider_choices_match_registry_order(self) -> None:
        # Picker order is deliberate (most-popular first); guard against
        # accidental reordering.
        choices = provider_choices()
        assert [c[0] for c in choices] == [p.id for p in PROVIDERS]

    def test_every_provider_has_at_least_one_model(self) -> None:
        # The picker only makes sense if each provider has a default
        # selection.
        for p in PROVIDERS:
            assert p.models, f"{p.id} has no models — picker would render empty"

    def test_curated_model_ids_present(self) -> None:
        # Spot-check that the v1.5.0-approved IDs are still in place.
        openai = get_provider("openai")
        assert openai is not None
        assert openai.models[0] == "gpt-5.5"

        anthropic = get_provider("anthropic")
        assert anthropic is not None
        assert anthropic.models[0] == "claude-sonnet-4-6"

        gemini = get_provider("gemini")
        assert gemini is not None
        assert gemini.models[0] == "gemini-3.1-pro"

        deepseek = get_provider("deepseek")
        assert deepseek is not None
        assert deepseek.models[0] == "deepseek-v4-pro"

        kimi = get_provider("kimi")
        assert kimi is not None
        assert kimi.models[0] == "kimi-k2.6"

        grok = get_provider("grok")
        assert grok is not None
        assert grok.models[0] == "grok-4.3"

    def test_get_provider_unknown_returns_none(self) -> None:
        assert get_provider("not-a-provider") is None

    def test_model_choices_carry_provider_display_name(self) -> None:
        # The meta column on each model completion shows the provider
        # display name — useful as a sanity check when the user is
        # navigating the dropdown.
        choices = model_choices("openai")
        assert choices
        for _model_id, meta in choices:
            assert meta == "OpenAI"

    def test_model_choices_unknown_provider_returns_empty(self) -> None:
        assert model_choices("nope") == []

    def test_provider_entries_are_frozen(self) -> None:
        # ProviderEntry is a frozen dataclass — mutation should error.
        p = ProviderEntry(
            id="x",
            display_name="X",
            env_var="X_KEY",
            api_key_url="",
            models=["a"],
        )
        import dataclasses

        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            p.id = "y"  # type: ignore[misc]
