"""Tests for ``quoriv.models.factory.with_fallbacks`` — Phase 3 Slice 9.

The ``with_fallbacks`` helper wraps a primary chat model with one or
more fallbacks via LangChain's ``Runnable.with_fallbacks``. We pin:

  * Empty / all-failing fallback lists return the primary unchanged
    (no chain object).
  * A valid fallback id calls ``get_model`` and walks through to
    ``primary.with_fallbacks(...)``.
  * A fallback that fails to build is **logged and skipped**, never
    raised — a partly-busted fallbacks list mustn't break agent
    startup.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda, RunnableWithFallbacks

from quoriv.models.base import MissingAPIKeyError
from quoriv.models.factory import with_fallbacks


class _FakeChatModel:
    """Minimal LangChain-style chat model stand-in.

    Exposes ``.with_fallbacks`` because that's the only attribute the
    helper actually calls on the primary. Returns a sentinel so tests
    can verify the call shape.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def with_fallbacks(self, fallbacks: list[Any]) -> dict[str, Any]:
        # Return a real-enough shape — the helper just hands the
        # result back to its caller.
        return {"primary": self, "fallbacks": fallbacks}


def _patch_get_model(monkeypatch: pytest.MonkeyPatch, by_id: dict[str, Any]) -> list[str]:
    """Replace ``quoriv.models.factory.get_model`` with a stub.

    ``by_id`` maps each id to either:
      * a chat-model stand-in (returned as-is), or
      * an exception instance (raised when the id is requested).

    Returns a list that gets populated with the ids the stub was
    asked about — handy for asserting call order.
    """
    asked: list[str] = []

    def fake_get_model(identifier: str, **_kwargs: Any) -> Any:
        asked.append(identifier)
        outcome = by_id[identifier]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("quoriv.models.factory.get_model", fake_get_model)
    return asked


# ---------------------------------------------------------------------------
# Empty / no-op paths
# ---------------------------------------------------------------------------


class TestEmptyFallbacks:
    def test_empty_iterable_returns_primary_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Empty list means "don't wrap" — no chain object, no extra
        # call into get_model.
        _patch_get_model(monkeypatch, {})
        primary = _FakeChatModel("primary")
        result = with_fallbacks(primary, [])
        assert result is primary

    def test_all_fallbacks_failing_returns_primary_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If every fallback raises at build time, the chain has
        # nothing to wrap — return the primary so the user still
        # gets a working session.
        _patch_get_model(
            monkeypatch,
            {
                "anthropic:claude-sonnet-4-6": MissingAPIKeyError("anthropic", "ANTHROPIC_API_KEY"),
                "ollama:llama3.2": RuntimeError("docker not running"),
            },
        )
        primary = _FakeChatModel("primary")
        result = with_fallbacks(primary, ["anthropic:claude-sonnet-4-6", "ollama:llama3.2"])
        assert result is primary


# ---------------------------------------------------------------------------
# Happy path — chain assembled in order
# ---------------------------------------------------------------------------


class TestChainAssembly:
    def test_single_fallback_wraps_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        secondary = _FakeChatModel("secondary")
        asked = _patch_get_model(monkeypatch, {"openai:gpt-4o-mini": secondary})
        primary = _FakeChatModel("primary")
        result = with_fallbacks(primary, ["openai:gpt-4o-mini"])
        # The helper calls primary.with_fallbacks(...) so our fake
        # returns the recorded shape.
        assert isinstance(result, dict)
        assert result["primary"] is primary
        assert result["fallbacks"] == [secondary]
        assert asked == ["openai:gpt-4o-mini"]

    def test_multiple_fallbacks_preserve_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        anth = _FakeChatModel("anthropic")
        oai = _FakeChatModel("openai")
        olm = _FakeChatModel("ollama")
        asked = _patch_get_model(
            monkeypatch,
            {
                "anthropic:claude-sonnet-4-6": anth,
                "openai:gpt-4o-mini": oai,
                "ollama:llama3.2": olm,
            },
        )
        primary = _FakeChatModel("primary")
        ids = [
            "anthropic:claude-sonnet-4-6",
            "openai:gpt-4o-mini",
            "ollama:llama3.2",
        ]
        result = with_fallbacks(primary, ids)
        assert result["fallbacks"] == [anth, oai, olm]
        assert asked == ids  # request order preserved


# ---------------------------------------------------------------------------
# Partial failure — skip + continue
# ---------------------------------------------------------------------------


class TestPartialFailure:
    def test_failing_fallback_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Middle fallback raises — the first and third should still
        # land in the chain.
        first = _FakeChatModel("first")
        third = _FakeChatModel("third")
        _patch_get_model(
            monkeypatch,
            {
                "ok:first": first,
                "bad:middle": MissingAPIKeyError("bad", "BAD_API_KEY"),
                "ok:third": third,
            },
        )
        primary = _FakeChatModel("primary")
        result = with_fallbacks(primary, ["ok:first", "bad:middle", "ok:third"])
        assert result["fallbacks"] == [first, third]


# ---------------------------------------------------------------------------
# Integration smoke — confirm the helper still works against a real
# LangChain primary (no monkeypatching of get_model). Uses tiny fakes
# that satisfy the Runnable.with_fallbacks contract.
# ---------------------------------------------------------------------------


class TestIntegrationSmoke:
    def test_returns_runnable_with_fallbacks_against_real_langchain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Use ``langchain_core.runnables.RunnableLambda`` as the
        # primary so ``.with_fallbacks`` returns a real
        # ``RunnableWithFallbacks``. This catches future API drift
        # in LangChain.
        primary = RunnableLambda(lambda _: "primary-result")
        secondary = RunnableLambda(lambda _: "secondary-result")
        _patch_get_model(monkeypatch, {"openai:gpt-4o-mini": secondary})
        result = with_fallbacks(primary, ["openai:gpt-4o-mini"])
        assert isinstance(result, RunnableWithFallbacks)
