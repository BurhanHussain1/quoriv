"""Per-provider token-cost rate table for ``/cost`` — Phase 1 Slice 9c.

:data:`RATES` maps ``provider:model`` prefixes to a :class:`ProviderRate`
holding USD-per-1,000-tokens for input and output. :func:`lookup_rate`
finds the entry that best matches a fully qualified model id by
**longest-prefix** match — so ``"openai:gpt-4o-mini"`` resolves to its
own entry rather than the broader ``"openai:gpt-4o"``.

The table is intentionally a Python literal rather than config: rates
change frequently and we want a single grep-able spot to update them.
The shipped values are approximate and current as of 2026-01; update
from each provider's pricing page when they change. Models the user
runs that aren't in the table render as ``rate not configured`` in
``/cost`` rather than guessing a wrong number.

For local-only providers (Ollama, vLLM) the rate is ``(0.0, 0.0)`` —
``/cost`` will still surface the token totals (useful for context
budgeting) but show a $0.00 estimate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderRate:
    """USD price per 1,000 tokens for one provider/model combination."""

    input_per_1k: float
    output_per_1k: float


# Approximate USD/1k-token rates. The keys are matched as **prefixes** of the
# fully qualified ``provider:model`` id, so adding a fine-grained entry for a
# specific model variant naturally wins over the broader provider entry via
# the longest-match rule in :func:`lookup_rate`.
RATES: dict[str, ProviderRate] = {
    # OpenAI
    "openai:gpt-5": ProviderRate(input_per_1k=0.0100, output_per_1k=0.0400),
    "openai:gpt-4o-mini": ProviderRate(input_per_1k=0.00015, output_per_1k=0.00060),
    "openai:gpt-4o": ProviderRate(input_per_1k=0.0025, output_per_1k=0.0100),
    "openai:gpt-4-turbo": ProviderRate(input_per_1k=0.0100, output_per_1k=0.0300),
    "openai:gpt-4": ProviderRate(input_per_1k=0.0300, output_per_1k=0.0600),
    "openai:gpt-3.5-turbo": ProviderRate(input_per_1k=0.0005, output_per_1k=0.0015),
    # Anthropic
    "anthropic:claude-opus-4": ProviderRate(input_per_1k=0.0150, output_per_1k=0.0750),
    "anthropic:claude-sonnet-4": ProviderRate(input_per_1k=0.0030, output_per_1k=0.0150),
    "anthropic:claude-haiku-4": ProviderRate(input_per_1k=0.0008, output_per_1k=0.0040),
    "anthropic:claude-3-5-sonnet": ProviderRate(input_per_1k=0.0030, output_per_1k=0.0150),
    "anthropic:claude-3-5-haiku": ProviderRate(input_per_1k=0.0008, output_per_1k=0.0040),
    "anthropic:claude-3-opus": ProviderRate(input_per_1k=0.0150, output_per_1k=0.0750),
    "anthropic:claude-3-haiku": ProviderRate(input_per_1k=0.00025, output_per_1k=0.00125),
    # Google Gemini
    "gemini:gemini-1.5-pro": ProviderRate(input_per_1k=0.00125, output_per_1k=0.0050),
    "gemini:gemini-1.5-flash": ProviderRate(input_per_1k=0.000075, output_per_1k=0.0003),
    # Local / self-hosted — no per-token billing.
    "ollama:": ProviderRate(input_per_1k=0.0, output_per_1k=0.0),
    "vllm:": ProviderRate(input_per_1k=0.0, output_per_1k=0.0),
}


def lookup_rate(model_id: str) -> ProviderRate | None:
    """Return the best (longest-prefix) :class:`ProviderRate` for ``model_id``.

    Args:
        model_id: A fully qualified id like ``"openai:gpt-5"`` or
            ``"anthropic:claude-sonnet-4"``. The same shape Quoriv uses
            elsewhere (provider colon model name).

    Returns:
        The rate entry whose key is the longest prefix of ``model_id``,
        or ``None`` if no key matches.
    """
    matches = [key for key in RATES if model_id.startswith(key)]
    if not matches:
        return None
    best = max(matches, key=len)
    return RATES[best]


def estimate_cost(
    rate: ProviderRate,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, float]:
    """Compute the dollar cost for a token count under ``rate``.

    Returns:
        ``{"input_cost_usd": float, "output_cost_usd": float,
          "total_cost_usd": float}``. All values are non-negative.
    """
    input_cost = (input_tokens / 1_000.0) * rate.input_per_1k
    output_cost = (output_tokens / 1_000.0) * rate.output_per_1k
    return {
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "total_cost_usd": input_cost + output_cost,
    }
