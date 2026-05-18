"""Google Gemini provider backend — Phase 3 Slice 3.

Builds a ``langchain_google_genai.ChatGoogleGenerativeAI`` instance,
resolving the API key through :mod:`quoriv.config.keychain`. The
keychain map already lists ``gemini`` (and ``google`` as an alias)
backed by the ``GOOGLE_API_KEY`` env var, so the precedence rules
match the other cloud providers (env var first, then OS keychain).

Requires the ``[gemini]`` install extra::

    pip install 'quoriv[gemini]'

Identifier shape: ``gemini:<model-name>``. Examples::

    get_model("gemini:gemini-1.5-flash")
    get_model("gemini:gemini-1.5-pro", temperature=0.0)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_google_genai import ChatGoogleGenerativeAI

from quoriv.config.keychain import PROVIDER_ENV_VARS, get_api_key
from quoriv.models.base import MissingAPIKeyError

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from quoriv.models.base import ModelSpec


PROVIDER_NAME = "gemini"


def build(spec: ModelSpec, **kwargs: Any) -> BaseChatModel:
    """Construct a ChatGoogleGenerativeAI instance for the given spec.

    Args:
        spec: Parsed model identifier (``spec.name`` is forwarded as
            the Gemini ``model`` parameter, e.g.
            ``"gemini-1.5-flash"``).
        **kwargs: Additional keyword arguments forwarded to
            ChatGoogleGenerativeAI (``temperature``,
            ``max_output_tokens``, etc.).

    Raises:
        MissingAPIKeyError: If neither ``GOOGLE_API_KEY`` nor a
            keychain entry can be found.
    """
    api_key = get_api_key(PROVIDER_NAME)
    if not api_key:
        raise MissingAPIKeyError(PROVIDER_NAME, PROVIDER_ENV_VARS[PROVIDER_NAME])

    return ChatGoogleGenerativeAI(model=spec.name, google_api_key=api_key, **kwargs)
