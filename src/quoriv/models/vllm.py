"""vLLM provider backend — Phase 3 Slice 4.

vLLM serves an OpenAI-compatible HTTP API, so under the hood the
provider builds a ``langchain_openai.ChatOpenAI`` instance pointed at
the user's vLLM endpoint via ``base_url``. The endpoint URL is
typically a self-hosted host (local box, k8s service, etc.), so the
provider works without network access at construction time —
connection errors surface at first invocation.

Defaults:

    ``base_url``   ``$VLLM_BASE_URL`` env var, else
                   ``http://localhost:8000/v1`` (the vLLM server's
                   default OpenAI-compatible endpoint).
    ``api_key``    ``$VLLM_API_KEY`` env var, then keychain, else the
                   placeholder ``"EMPTY"``. Many vLLM deployments
                   don't enforce auth on local networks; we never
                   raise :class:`MissingAPIKeyError` for vLLM because
                   a placeholder is good enough for the API client
                   to function.

Both can be overridden via ``**kwargs``::

    get_model("vllm:my-finetune", base_url="http://gpu-box:8000/v1")
    get_model("vllm:llama3", api_key="my-vllm-token")

Requires the OpenAI SDK (already a core Quoriv dep — no extra needed).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from langchain_openai import ChatOpenAI

from quoriv.config.keychain import get_api_key

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from quoriv.models.base import ModelSpec


PROVIDER_NAME = "vllm"

_DEFAULT_BASE_URL = "http://localhost:8000/v1"
"""Endpoint the vLLM OpenAI-compatible server uses out of the box."""

_PLACEHOLDER_API_KEY = "EMPTY"
"""``ChatOpenAI`` requires *some* string; vLLM ignores it on unauth servers."""


def build(spec: ModelSpec, **kwargs: Any) -> BaseChatModel:
    """Construct a ChatOpenAI pointed at a vLLM endpoint.

    Args:
        spec: Parsed model identifier (``spec.name`` is forwarded as
            the OpenAI ``model`` parameter — typically the model id
            the vLLM server is serving, e.g. ``"llama3"`` or
            ``"my-finetune"``).
        **kwargs: Additional keyword arguments forwarded to
            ChatOpenAI. ``base_url`` and ``api_key`` get sensible
            defaults if not supplied here.

    Returns:
        A configured ``ChatOpenAI`` instance. No network call is made
        at construction time.
    """
    # Default base_url precedence: explicit kwarg > $VLLM_BASE_URL >
    # built-in localhost default. Pop from kwargs so we don't pass it
    # twice to ChatOpenAI.
    base_url = kwargs.pop("base_url", None) or os.environ.get("VLLM_BASE_URL", _DEFAULT_BASE_URL)
    # Default api_key precedence: explicit kwarg > keychain (env-or-store)
    # > placeholder. vLLM endpoints frequently run without auth, so
    # never raise on a missing key — fall through to the placeholder.
    api_key = kwargs.pop("api_key", None) or get_api_key(PROVIDER_NAME) or _PLACEHOLDER_API_KEY

    return ChatOpenAI(model=spec.name, api_key=api_key, base_url=base_url, **kwargs)
