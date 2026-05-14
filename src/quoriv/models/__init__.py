"""Model provider abstraction.

Wraps LangChain chat models behind a uniform interface so the agent can
swap between OpenAI, Anthropic, Google Gemini, Ollama, vLLM, and OpenRouter
without code changes.

Phase 1 (current): OpenAI provider.
Phase 3: All other providers.
"""

from __future__ import annotations

from quoriv.models.base import (
    MissingAPIKeyError,
    ModelCapabilities,
    ModelSpec,
)
from quoriv.models.factory import (
    UnknownProviderError,
    get_model,
    list_providers,
)

__all__ = [
    "MissingAPIKeyError",
    "ModelCapabilities",
    "ModelSpec",
    "UnknownProviderError",
    "get_model",
    "list_providers",
]
