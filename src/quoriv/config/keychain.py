"""API key storage via OS keychain with environment-variable fallback.

Quoriv never writes API keys to disk in plaintext. Keys are stored either
in the operating system's keychain (via the ``keyring`` library) or
supplied through provider-specific environment variables.

Resolution order when fetching a key:

    1. Provider-specific environment variable (e.g. ``OPENAI_API_KEY``).
       Useful for CI, containers, and one-off overrides.
    2. OS keychain entry under the ``quoriv`` service.

Set a key from the CLI (once the CLI lands in Day 4):

    quoriv config set openai

That command shells out to :func:`set_api_key` here.
"""

from __future__ import annotations

import os
from typing import Final

import keyring
import keyring.errors

SERVICE_NAME: Final = "quoriv"
"""Service name used for keychain entries (the ``service`` in ``service/username``)."""


PROVIDER_ENV_VARS: Final[dict[str, str]] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
    "vllm": "VLLM_API_KEY",
    # Phase 3 Slice 7: Tavily backs the ``web_search`` tool. Not a
    # model provider per se, but the key-resolution flow is the same
    # (env var first, then keychain) so we register it here.
    "tavily": "TAVILY_API_KEY",
}
"""Provider name -> environment variable consulted as a key source.

Providers absent from this map (e.g. ``ollama``) typically run locally and
do not require an API key. Search backends that need keys (Tavily) also
live here.
"""


def set_api_key(provider: str, key: str) -> None:
    """Store an API key in the OS keychain.

    Raises:
        keyring.errors.PasswordSetError: If the backend refuses to store
            the secret (rare on supported platforms).
    """
    keyring.set_password(SERVICE_NAME, provider, key)


def get_api_key(provider: str) -> str | None:
    """Retrieve an API key for ``provider``.

    Resolution order:
        1. ``PROVIDER_ENV_VARS[provider]`` from ``os.environ``.
        2. ``keyring`` entry under the ``quoriv`` service.

    Returns:
        The key string, or ``None`` if neither source provides one.
    """
    env_var = PROVIDER_ENV_VARS.get(provider)
    if env_var:
        env_value = os.environ.get(env_var)
        if env_value:
            return env_value

    try:
        return keyring.get_password(SERVICE_NAME, provider)
    except keyring.errors.KeyringError:
        return None


def delete_api_key(provider: str) -> bool:
    """Remove a stored API key from the keychain.

    Returns:
        ``True`` if a key was deleted, ``False`` if no key was stored or
        the backend refused the deletion.

    Note:
        Only removes the keychain entry; environment-variable values are
        not affected.
    """
    try:
        keyring.delete_password(SERVICE_NAME, provider)
    except keyring.errors.PasswordDeleteError:
        return False
    except keyring.errors.KeyringError:
        return False
    return True


def list_known_providers() -> list[str]:
    """Return the sorted list of provider names recognized for key storage.

    Useful for CLI autocomplete and ``quoriv doctor`` output.
    """
    return sorted(PROVIDER_ENV_VARS.keys())
