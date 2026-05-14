"""Model provider abstraction.

This module defines the building blocks shared by every provider:

    ModelSpec           A parsed ``"provider:name"`` identifier.
    ModelCapabilities   Static facts about a specific model (used by routing).
    MissingAPIKeyError  Raised when a provider can't find its key.

Concrete provider modules (``quoriv.models.openai``, ``quoriv.models.anthropic``,
...) expose a top-level ``build(spec, **kwargs) -> BaseChatModel`` callable.
The dispatcher in :mod:`quoriv.models.factory` resolves the right builder.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """A parsed model identifier of the form ``"provider:name"``.

    Model names may themselves contain colons (e.g. Ollama tags), so the
    identifier is split on the *first* colon only::

        ModelSpec.parse("ollama:qwen2.5-coder:32b")
        # -> ModelSpec(provider="ollama", name="qwen2.5-coder:32b")
    """

    provider: str
    name: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.name}"

    @classmethod
    def parse(cls, identifier: str) -> ModelSpec:
        """Parse a ``"provider:name"`` identifier.

        Raises:
            ValueError: If the identifier is empty, contains no colon, or
                has an empty provider/name half.
        """
        if not identifier:
            raise ValueError("Model identifier is empty.")
        if ":" not in identifier:
            raise ValueError(f"Model identifier must be 'provider:name', got: {identifier!r}")
        provider, _, name = identifier.partition(":")
        if not provider or not name:
            raise ValueError(f"Both provider and name must be non-empty: {identifier!r}")
        return cls(provider=provider, name=name)


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Static capabilities of a model.

    Populated by each provider so the routing layer can make informed
    decisions — e.g. don't send a tool-using task to a model without
    tool support, or a vision task to a text-only model.
    """

    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    context_window: int | None = None  # tokens; None means unknown


class MissingAPIKeyError(RuntimeError):
    """Raised when a provider cannot resolve its API key from any source."""

    def __init__(self, provider: str, env_var: str) -> None:
        super().__init__(
            f"No API key found for provider {provider!r}. "
            f"Set ${env_var} or run 'quoriv config set {provider}'."
        )
        self.provider = provider
        self.env_var = env_var
