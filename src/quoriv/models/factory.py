"""Model factory — entry point for getting a configured chat model.

Usage::

    from quoriv.models import get_model

    llm = get_model("openai:gpt-4.1")
    llm = get_model("openai:gpt-4o-mini", temperature=0.0)

Providers are imported lazily so users don't pay the LangChain / SDK
import cost for backends they aren't using.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, cast

from quoriv.models.base import ModelSpec

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain_core.language_models import BaseChatModel

    BuilderFn = Callable[..., BaseChatModel]


# Provider name -> "module:attribute" string for the builder callable.
# Lazy so importing this module is cheap.
_PROVIDERS: dict[str, str] = {
    "openai": "quoriv.models.openai:build",
    "anthropic": "quoriv.models.anthropic:build",
    "ollama": "quoriv.models.ollama:build",
    "gemini": "quoriv.models.gemini:build",
    "vllm": "quoriv.models.vllm:build",
    "openrouter": "quoriv.models.openrouter:build",
}


class UnknownProviderError(RuntimeError):
    """Raised when a requested provider is not registered."""

    def __init__(self, provider: str, known: list[str]) -> None:
        super().__init__(
            f"Unknown model provider {provider!r}. "
            f"Known providers: {', '.join(known) if known else '(none)'}."
        )
        self.provider = provider
        self.known = known


def get_model(identifier: str, **kwargs: Any) -> BaseChatModel:
    """Build a chat model from a ``"provider:name"`` identifier.

    Examples::

        get_model("openai:gpt-4.1")
        get_model("openai:gpt-4o-mini", temperature=0.0, max_tokens=512)

    Args:
        identifier: Model identifier in ``"provider:name"`` form.
        **kwargs: Provider-specific keyword arguments forwarded to the
            underlying LangChain model constructor.

    Raises:
        ValueError: If the identifier is malformed.
        UnknownProviderError: If the provider name is not registered.
        MissingAPIKeyError: If the provider needs a key it cannot find.
    """
    spec = ModelSpec.parse(identifier)
    builder = _load_builder(spec.provider)
    return builder(spec, **kwargs)


def list_providers() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(_PROVIDERS.keys())


def _load_builder(provider: str) -> BuilderFn:
    """Resolve a provider name to its ``build`` callable, importing lazily."""
    spec_str = _PROVIDERS.get(provider)
    if spec_str is None:
        raise UnknownProviderError(provider, list_providers())
    module_path, _, attr = spec_str.partition(":")
    module = importlib.import_module(module_path)
    return cast("BuilderFn", getattr(module, attr))
