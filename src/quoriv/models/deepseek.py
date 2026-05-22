"""DeepSeek provider backend.

DeepSeek serves an OpenAI-compatible API at ``https://api.deepseek.com``,
so we route through :class:`langchain_openai.ChatOpenAI` with a custom
``base_url``. The provider name (``"deepseek"``) is what keys the
keychain entry and the env var (``DEEPSEEK_API_KEY``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_openai import ChatOpenAI

from quoriv.config.keychain import PROVIDER_ENV_VARS, get_api_key
from quoriv.models.base import MissingAPIKeyError, ModelSpec

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


PROVIDER_NAME = "deepseek"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def build(spec: ModelSpec, **kwargs: Any) -> BaseChatModel:
    """Construct a ChatOpenAI instance pointed at DeepSeek's endpoint."""
    api_key = get_api_key(PROVIDER_NAME)
    if not api_key:
        raise MissingAPIKeyError(PROVIDER_NAME, PROVIDER_ENV_VARS[PROVIDER_NAME])
    base_url = kwargs.pop("base_url", DEFAULT_BASE_URL)
    return ChatOpenAI(model=spec.name, api_key=api_key, base_url=base_url, **kwargs)
