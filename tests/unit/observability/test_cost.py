"""Tests for `quoriv.observability.cost`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from quoriv.config.schema import QuorivConfig
from quoriv.observability.cost import (
    RATES,
    ProviderRate,
    effective_rates,
    estimate_cost,
    lookup_rate,
)

# ---------------------------------------------------------------------------
# ProviderRate dataclass
# ---------------------------------------------------------------------------


class TestProviderRate:
    def test_is_frozen(self) -> None:
        rate = ProviderRate(input_per_1k=0.01, output_per_1k=0.03)
        with pytest.raises(FrozenInstanceError):
            rate.input_per_1k = 0.02  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        assert ProviderRate(0.01, 0.03) == ProviderRate(0.01, 0.03)
        assert ProviderRate(0.01, 0.03) != ProviderRate(0.02, 0.03)


# ---------------------------------------------------------------------------
# RATES table sanity
# ---------------------------------------------------------------------------


class TestRatesTable:
    def test_has_entries(self) -> None:
        assert len(RATES) > 0

    def test_every_entry_is_provider_rate(self) -> None:
        assert all(isinstance(v, ProviderRate) for v in RATES.values())

    def test_rates_are_non_negative(self) -> None:
        for key, rate in RATES.items():
            assert rate.input_per_1k >= 0, f"{key} has negative input rate"
            assert rate.output_per_1k >= 0, f"{key} has negative output rate"

    def test_known_providers_present(self) -> None:
        # The README and CHANGELOG name these providers explicitly; make
        # sure at least one entry per provider stays in the table so
        # ``/cost`` doesn't silently regress for them.
        providers = {key.split(":", 1)[0] for key in RATES}
        for provider in ("openai", "anthropic", "gemini", "ollama"):
            assert provider in providers

    def test_keys_use_provider_colon_model_shape(self) -> None:
        # Either "provider:model" (most rows) or "provider:" (the
        # local-only sentinels). All keys must contain a colon.
        for key in RATES:
            assert ":" in key, f"key {key!r} missing provider colon"


# ---------------------------------------------------------------------------
# lookup_rate
# ---------------------------------------------------------------------------


class TestLookupRate:
    def test_exact_match(self) -> None:
        rate = lookup_rate("openai:gpt-5")
        assert rate is not None
        assert rate == RATES["openai:gpt-5"]

    def test_longest_prefix_wins(self) -> None:
        # "openai:gpt-4o-mini" should resolve to its own rate, not to the
        # broader "openai:gpt-4o" entry.
        rate = lookup_rate("openai:gpt-4o-mini")
        assert rate == RATES["openai:gpt-4o-mini"]
        # Sanity: the broader prefix has a different rate.
        assert RATES["openai:gpt-4o-mini"] != RATES["openai:gpt-4o"]

    def test_versioned_suffix_matches_prefix(self) -> None:
        # An id like "openai:gpt-4o-2024-08-06" should fall back to the
        # "openai:gpt-4o" prefix.
        rate = lookup_rate("openai:gpt-4o-2024-08-06")
        assert rate == RATES["openai:gpt-4o"]

    def test_ollama_any_model(self) -> None:
        # The "ollama:" sentinel matches every model name.
        rate = lookup_rate("ollama:llama3.2:latest")
        assert rate is not None
        assert rate.input_per_1k == 0.0
        assert rate.output_per_1k == 0.0

    def test_unknown_provider_returns_none(self) -> None:
        assert lookup_rate("xyz:nothing") is None

    def test_empty_id_returns_none(self) -> None:
        assert lookup_rate("") is None


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_zero_tokens(self) -> None:
        rate = ProviderRate(input_per_1k=0.01, output_per_1k=0.03)
        result = estimate_cost(rate, 0, 0)
        assert result == {
            "input_cost_usd": 0.0,
            "output_cost_usd": 0.0,
            "total_cost_usd": 0.0,
        }

    def test_basic_math(self) -> None:
        rate = ProviderRate(input_per_1k=0.01, output_per_1k=0.03)
        result = estimate_cost(rate, 1_000, 2_000)
        # 1k input @ $0.01 + 2k output @ $0.03 = $0.07
        assert result["input_cost_usd"] == pytest.approx(0.01)
        assert result["output_cost_usd"] == pytest.approx(0.06)
        assert result["total_cost_usd"] == pytest.approx(0.07)

    def test_sub_thousand_tokens(self) -> None:
        rate = ProviderRate(input_per_1k=0.01, output_per_1k=0.03)
        # 500 input tokens at $0.01/1k = $0.005
        result = estimate_cost(rate, 500, 0)
        assert result["input_cost_usd"] == pytest.approx(0.005)

    def test_free_rate_zeros_out(self) -> None:
        rate = ProviderRate(input_per_1k=0.0, output_per_1k=0.0)
        result = estimate_cost(rate, 1_000_000, 1_000_000)
        assert result["total_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# lookup_rate — custom-table arg (Slice 9d)
# ---------------------------------------------------------------------------


class TestLookupRateCustomTable:
    def test_uses_supplied_table_not_builtin(self) -> None:
        # The custom table has only one entry. The lookup must consult
        # *this* table, not the module-level RATES, so a model that
        # exists in RATES but not in the custom table returns None.
        custom = {"acme:foo": ProviderRate(input_per_1k=1.0, output_per_1k=2.0)}
        assert lookup_rate("acme:foo", custom) == custom["acme:foo"]
        assert lookup_rate("openai:gpt-5", custom) is None

    def test_longest_prefix_within_custom_table(self) -> None:
        custom = {
            "openai:gpt-4o": ProviderRate(input_per_1k=0.01, output_per_1k=0.02),
            "openai:gpt-4o-mini": ProviderRate(input_per_1k=0.001, output_per_1k=0.002),
        }
        assert lookup_rate("openai:gpt-4o-mini", custom) == custom["openai:gpt-4o-mini"]
        assert lookup_rate("openai:gpt-4o-2024-08-06", custom) == custom["openai:gpt-4o"]

    def test_none_arg_falls_back_to_builtin(self) -> None:
        # Explicitly passing None must behave like the legacy single-arg
        # form, so existing callers stay unaffected.
        assert lookup_rate("openai:gpt-5", None) == RATES["openai:gpt-5"]


# ---------------------------------------------------------------------------
# effective_rates — Slice 9d
# ---------------------------------------------------------------------------


class TestEffectiveRates:
    def test_none_config_returns_builtins_copy(self) -> None:
        table = effective_rates(None)
        # Same content as the built-in table.
        assert table == RATES
        # But a fresh dict: mutating the return value must not bleed
        # back into the module-level RATES.
        table["openai:gpt-5"] = ProviderRate(input_per_1k=999.0, output_per_1k=999.0)
        assert RATES["openai:gpt-5"] != table["openai:gpt-5"]

    def test_empty_config_matches_builtins(self) -> None:
        config = QuorivConfig.model_validate({})
        assert effective_rates(config) == RATES

    def test_user_override_replaces_builtin(self) -> None:
        config = QuorivConfig.model_validate(
            {"cost": {"rates": {"openai:gpt-5": {"input_per_1k": 0.05, "output_per_1k": 0.20}}}}
        )
        table = effective_rates(config)
        assert table["openai:gpt-5"] == ProviderRate(input_per_1k=0.05, output_per_1k=0.20)
        # Other built-in entries survive the merge.
        assert table["anthropic:claude-opus-4"] == RATES["anthropic:claude-opus-4"]

    def test_user_can_add_new_provider(self) -> None:
        config = QuorivConfig.model_validate(
            {
                "cost": {
                    "rates": {"acme:test-model": {"input_per_1k": 0.001, "output_per_1k": 0.002}}
                }
            }
        )
        table = effective_rates(config)
        assert table["acme:test-model"] == ProviderRate(input_per_1k=0.001, output_per_1k=0.002)
        # Lookup against the merged table resolves the new provider.
        assert lookup_rate("acme:test-model", table) == table["acme:test-model"]

    def test_does_not_mutate_module_rates(self) -> None:
        # Sanity guard against an accidental ``RATES.update(...)`` slip
        # in effective_rates — would cause cross-test contamination.
        original_keys = set(RATES)
        original_gpt5 = RATES["openai:gpt-5"]
        config = QuorivConfig.model_validate(
            {"cost": {"rates": {"openai:gpt-5": {"input_per_1k": 9.99, "output_per_1k": 9.99}}}}
        )
        effective_rates(config)
        assert set(RATES) == original_keys
        assert RATES["openai:gpt-5"] == original_gpt5

    def test_more_specific_user_key_wins_over_builtin_prefix(self) -> None:
        # User adds a fine-grained key under a broader built-in prefix.
        # Longest-prefix lookup in the merged table must pick the user's
        # key — that's the whole point of config-driven overrides.
        config = QuorivConfig.model_validate(
            {
                "cost": {
                    "rates": {
                        "anthropic:claude-opus-4-7": {
                            "input_per_1k": 0.020,
                            "output_per_1k": 0.080,
                        }
                    }
                }
            }
        )
        table = effective_rates(config)
        # The built-in has only "anthropic:claude-opus-4".
        result = lookup_rate("anthropic:claude-opus-4-7", table)
        assert result == ProviderRate(input_per_1k=0.020, output_per_1k=0.080)
