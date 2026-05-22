"""Curated provider + model registry for the ``/login`` onboarding flow.

The registry pairs each first-class provider with:

* its display name (shown in the picker)
* the matching keychain service / env var (so the onboarding flow can
  store the user-supplied API key under the right name)
* a *short, curated* list of recommended models — what the picker
  surfaces after the user has saved their key. The IDs come from the
  May 2026 round-up the user approved; the first entry is the default
  selection.

Keep this file *static*. The goal is "user picks from a small, vetted
list of current models" — not "live-discover everything the provider
exposes via ``models.list()``". When a new generation ships, bump the
entries here. The trade-off vs runtime discovery is documented in
``CHANGELOG.md`` under v1.5.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ProviderEntry:
    """One row in the provider picker.

    Attributes:
        id: Short identifier used in ``provider:model`` config strings
            (``"openai"``, ``"anthropic"``, ``"deepseek"``, …).
        display_name: Human-readable label for the dropdown.
        env_var: Environment variable consulted by the keychain (same
            as the matching entry in ``PROVIDER_ENV_VARS`` — duplicated
            here so the onboarding UI can surface it in error
            messages).
        api_key_url: Page the user can open to grab a fresh API key.
            Empty string if there is no canonical page.
        models: Ordered recommended model list. The first entry is the
            default highlighted choice in the model picker.
    """

    id: str
    display_name: str
    env_var: str
    api_key_url: str
    models: list[str] = field(default_factory=list)


PROVIDERS: list[ProviderEntry] = [
    ProviderEntry(
        id="openai",
        display_name="OpenAI",
        env_var="OPENAI_API_KEY",
        api_key_url="https://platform.openai.com/api-keys",
        models=[
            "gpt-5.5",
            "gpt-5.5-pro",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
        ],
    ),
    ProviderEntry(
        id="anthropic",
        display_name="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        api_key_url="https://console.anthropic.com/settings/keys",
        models=[
            "claude-sonnet-4-6",
            "claude-opus-4-7",
            "claude-haiku-4-5-20251001",
        ],
    ),
    ProviderEntry(
        id="gemini",
        display_name="Google Gemini",
        env_var="GOOGLE_API_KEY",
        api_key_url="https://aistudio.google.com/apikey",
        models=[
            "gemini-3.1-pro",
            "gemini-3.5-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ],
    ),
    ProviderEntry(
        id="deepseek",
        display_name="DeepSeek",
        env_var="DEEPSEEK_API_KEY",
        api_key_url="https://platform.deepseek.com/api_keys",
        models=[
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-v3.1",
            "deepseek-r1",
        ],
    ),
    ProviderEntry(
        id="kimi",
        display_name="Kimi (Moonshot AI)",
        env_var="MOONSHOT_API_KEY",
        api_key_url="https://platform.moonshot.ai/console/api-keys",
        models=[
            "kimi-k2.6",
            "kimi-k2.5",
        ],
    ),
    ProviderEntry(
        id="grok",
        display_name="xAI Grok",
        env_var="XAI_API_KEY",
        api_key_url="https://console.x.ai/",
        models=[
            "grok-4.3",
            "grok-4.20-non-reasoning",
        ],
    ),
]
"""Ordered list of supported providers — order is what the user sees."""


_BY_ID: dict[str, ProviderEntry] = {p.id: p for p in PROVIDERS}


def get_provider(provider_id: str) -> ProviderEntry | None:
    """Return the registry entry for ``provider_id``, or ``None`` if absent."""
    return _BY_ID.get(provider_id)


def provider_choices() -> list[tuple[str, str]]:
    """Return ``(id, label)`` pairs in display order for the picker."""
    return [(p.id, p.display_name) for p in PROVIDERS]


def model_choices(provider_id: str) -> list[tuple[str, str]]:
    """Return ``(model_id, label)`` pairs for the given provider.

    Labels are just the model id — the description column in the
    completion popup carries the provider name as a sanity check.
    Empty list if the provider is unknown.
    """
    entry = _BY_ID.get(provider_id)
    if entry is None:
        return []
    return [(m, entry.display_name) for m in entry.models]
