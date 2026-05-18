"""OpenRouter provider backend — Phase 3 Slice 5.

OpenRouter is a routing layer that exposes hundreds of models from
different providers (Anthropic, OpenAI, Mistral, Meta, …) through a
single OpenAI-compatible API. We build a
``langchain_openai.ChatOpenAI`` instance pointed at
``https://openrouter.ai/api/v1`` — same pattern as the vLLM provider
but with a fixed cloud endpoint and a required API key.

Requires no extra install — the OpenAI SDK is already a core Quoriv
dependency.

Identifier shape: ``openrouter:<vendor>/<model>``. The vendor / model
slash is part of the *name* half; ``ModelSpec.parse`` splits on the
first colon only, so the slash flows through unchanged::

    get_model("openrouter:anthropic/claude-3.5-sonnet")
    get_model("openrouter:meta-llama/llama-3.1-405b-instruct")

API-key resolution follows the standard Quoriv precedence (env var
``OPENROUTER_API_KEY`` first, then OS keychain). Unlike vLLM, the key
is **required** — OpenRouter is a paid service and the SDK rejects
unauthenticated requests at the API layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_openai import ChatOpenAI

from quoriv.config.keychain import PROVIDER_ENV_VARS, get_api_key
from quoriv.models.base import MissingAPIKeyError

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from quoriv.models.base import ModelSpec


PROVIDER_NAME = "openrouter"

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
"""Fixed cloud endpoint — OpenRouter does not have alternate hosts."""


def build(spec: ModelSpec, **kwargs: Any) -> BaseChatModel:
    """Construct a ChatOpenAI instance pointed at OpenRouter.

    Args:
        spec: Parsed model identifier (``spec.name`` is forwarded as
            the OpenAI ``model`` parameter — for OpenRouter this is
            typically ``"<vendor>/<model>"``, e.g.
            ``"anthropic/claude-3.5-sonnet"``).
        **kwargs: Additional keyword arguments forwarded to
            ChatOpenAI. ``base_url`` defaults to OpenRouter's
            endpoint; pass an explicit kwarg to override (rare).

    Raises:
        MissingAPIKeyError: If neither ``OPENROUTER_API_KEY`` nor a
            keychain entry can be found.
    """
    api_key = get_api_key(PROVIDER_NAME)
    if not api_key:
        raise MissingAPIKeyError(PROVIDER_NAME, PROVIDER_ENV_VARS[PROVIDER_NAME])

    # ``base_url`` from kwargs wins so users can target OpenRouter
    # proxies or staging endpoints if they need to.
    base_url = kwargs.pop("base_url", None) or _OPENROUTER_BASE_URL
    return ChatOpenAI(model=spec.name, api_key=api_key, base_url=base_url, **kwargs)
