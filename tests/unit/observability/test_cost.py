"""Tests for `quoriv.observability.cost`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from quoriv.observability.cost import (
    RATES,
    ProviderRate,
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
