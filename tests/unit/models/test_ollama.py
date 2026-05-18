"""Tests for ``quoriv.models.ollama`` — Phase 3 Slice 2.

Unlike the Anthropic and OpenAI providers, Ollama runs locally and
does **not** require an API key — so the test surface is a touch
narrower (no missing-key path, no env-var precedence). The Ollama-
specific quirk we care about: model names carry a colon for the
tag (``qwen2.5-coder:32b``), which the ``provider:name`` parser
must keep intact by splitting on the first colon only.
"""

from __future__ import annotations

import pytest
from langchain_ollama import ChatOllama

from quoriv.models.base import ModelSpec
from quoriv.models.ollama import build

# ---------------------------------------------------------------------------
# Construction — no API key required
# ---------------------------------------------------------------------------


class TestBuild:
    def test_returns_chat_ollama(self) -> None:
        # ``fake_keyring`` is intentionally absent: Ollama doesn't
        # touch the keychain. The provider must build cleanly with
        # zero secrets configured.
        spec = ModelSpec.parse("ollama:llama3.2")
        model = build(spec)
        assert isinstance(model, ChatOllama)
        assert getattr(model, "model", None) == "llama3.2"

    def test_no_network_call_at_construction(self) -> None:
        # ``ChatOllama(model=...)`` is purely constructive — the
        # actual HTTP call to the Ollama server happens at first
        # invocation. We rely on this so ``build_agent`` can succeed
        # in environments where Ollama isn't running yet.
        spec = ModelSpec.parse("ollama:never-pulled-model")
        model = build(spec)
        # No exception raised; instance is healthy.
        assert isinstance(model, ChatOllama)


# ---------------------------------------------------------------------------
# Model name preservation — Ollama tags carry an embedded colon
# ---------------------------------------------------------------------------


class TestModelNameWithTag:
    def test_tag_colon_preserved(self) -> None:
        # The second colon is part of the model *name*, not a
        # provider separator. ``ModelSpec.parse`` documents this by
        # splitting on the first colon only.
        spec = ModelSpec.parse("ollama:qwen2.5-coder:32b")
        assert spec.provider == "ollama"
        assert spec.name == "qwen2.5-coder:32b"
        model = build(spec)
        assert getattr(model, "model", None) == "qwen2.5-coder:32b"

    def test_tag_colon_with_size_suffix(self) -> None:
        # Real-world Ollama identifier shape.
        spec = ModelSpec.parse("ollama:llama3.1:70b-instruct-q4_0")
        model = build(spec)
        assert getattr(model, "model", None) == "llama3.1:70b-instruct-q4_0"


# ---------------------------------------------------------------------------
# kwargs forwarding
# ---------------------------------------------------------------------------


class TestKwargsForwarded:
    def test_base_url_forwarded(self) -> None:
        # ``base_url`` is the key knob for pointing at a non-default
        # Ollama host (Docker, remote box, etc.).
        spec = ModelSpec.parse("ollama:llama3.2")
        model = build(spec, base_url="http://my-host:11434")
        # The attribute is exposed by the LangChain wrapper, name may
        # be base_url or ollama_host depending on lib version.
        actual = getattr(model, "base_url", None) or getattr(model, "ollama_host", None)
        assert actual == "http://my-host:11434"

    def test_temperature_forwarded(self) -> None:
        spec = ModelSpec.parse("ollama:llama3.2")
        model = build(spec, temperature=0.0)
        assert getattr(model, "temperature", None) == pytest.approx(0.0)
