"""Ollama provider backend — Phase 3 Slice 2.

Builds a ``langchain_ollama.ChatOllama`` instance pointed at a local
or remote Ollama server. Ollama runs the model locally (or on a host
the user controls), so **no API key is required** — the provider is
intentionally absent from
:data:`quoriv.config.keychain.PROVIDER_ENV_VARS`.

Requires the ``[ollama]`` install extra::

    pip install 'quoriv[ollama]'

Identifier shape: ``ollama:<model-name>[:tag]``. Model names may
themselves carry a colon for the tag (``qwen2.5-coder:32b``), which
:meth:`ModelSpec.parse` preserves because it splits on the *first*
colon only::

    get_model("ollama:qwen2.5-coder:32b")
    get_model("ollama:llama3.2", base_url="http://my-host:11434")

The default ``base_url`` (``http://localhost:11434``) is supplied by
``ChatOllama`` itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_ollama import ChatOllama

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from quoriv.models.base import ModelSpec


PROVIDER_NAME = "ollama"


def build(spec: ModelSpec, **kwargs: Any) -> BaseChatModel:
    """Construct a ChatOllama instance for the given spec.

    Args:
        spec: Parsed model identifier (``spec.name`` is forwarded as
            the Ollama ``model`` parameter, e.g.
            ``"qwen2.5-coder:32b"`` or ``"llama3.2"``).
        **kwargs: Additional keyword arguments forwarded to
            ChatOllama (``base_url``, ``temperature``, ``num_ctx``,
            etc.).

    Returns:
        A configured ``ChatOllama`` instance. No network call is made
        at construction time — connection errors surface at first
        invocation.
    """
    return ChatOllama(model=spec.name, **kwargs)
