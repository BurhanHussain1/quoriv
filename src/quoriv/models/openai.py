"""OpenAI provider backend.

Builds a ``langchain_openai.ChatOpenAI`` instance, resolving the API key
through :mod:`quoriv.config.keychain` (env var first, then OS keychain).

For Azure OpenAI or self-hosted OpenAI-compatible endpoints, pass
``base_url=...`` through ``**kwargs``::

    get_model("openai:gpt-4.1", base_url="https://my.azure.endpoint/")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_openai import ChatOpenAI

from quoriv.config.keychain import PROVIDER_ENV_VARS, get_api_key
from quoriv.models.base import MissingAPIKeyError, ModelSpec

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


PROVIDER_NAME = "openai"


def build(spec: ModelSpec, **kwargs: Any) -> BaseChatModel:
    """Construct a ChatOpenAI instance for the given spec.

    Args:
        spec: Parsed model identifier (``spec.name`` is forwarded as
            the OpenAI ``model`` parameter, e.g. ``"gpt-4.1"``).
        **kwargs: Additional keyword arguments forwarded to ChatOpenAI
            (``temperature``, ``max_tokens``, ``base_url``, etc.).

    Raises:
        MissingAPIKeyError: If neither ``OPENAI_API_KEY`` nor a keychain
            entry can be found.
    """
    api_key = get_api_key(PROVIDER_NAME)
    if not api_key:
        raise MissingAPIKeyError(PROVIDER_NAME, PROVIDER_ENV_VARS[PROVIDER_NAME])

    return ChatOpenAI(model=spec.name, api_key=api_key, **kwargs)
