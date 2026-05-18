"""Anthropic provider backend — Phase 3 Slice 1.

Builds a ``langchain_anthropic.ChatAnthropic`` instance, resolving the
API key through :mod:`quoriv.config.keychain` (env var first, then OS
keychain) — same precedence the OpenAI provider uses.

Requires the ``[anthropic]`` install extra::

    pip install 'quoriv[anthropic]'

Identifier shape: ``anthropic:<model-name>``. Examples::

    get_model("anthropic:claude-sonnet-4-6")
    get_model("anthropic:claude-opus-4-7", temperature=0.0)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_anthropic import ChatAnthropic

from quoriv.config.keychain import PROVIDER_ENV_VARS, get_api_key
from quoriv.models.base import MissingAPIKeyError, ModelSpec

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


PROVIDER_NAME = "anthropic"


def build(spec: ModelSpec, **kwargs: Any) -> BaseChatModel:
    """Construct a ChatAnthropic instance for the given spec.

    Args:
        spec: Parsed model identifier (``spec.name`` is forwarded as
            the Anthropic ``model`` parameter, e.g.
            ``"claude-sonnet-4-6"``).
        **kwargs: Additional keyword arguments forwarded to
            ChatAnthropic (``temperature``, ``max_tokens``,
            ``base_url``, etc.).

    Raises:
        MissingAPIKeyError: If neither ``ANTHROPIC_API_KEY`` nor a
            keychain entry can be found.
    """
    api_key = get_api_key(PROVIDER_NAME)
    if not api_key:
        raise MissingAPIKeyError(PROVIDER_NAME, PROVIDER_ENV_VARS[PROVIDER_NAME])

    return ChatAnthropic(model=spec.name, api_key=api_key, **kwargs)
