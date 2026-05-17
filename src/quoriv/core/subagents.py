"""Built-in subagents and model routing — Phase 2 Slice 4.

Quoriv ships three built-in subagents that the main agent delegates
to via DeepAgents' ``task`` tool:

    ``researcher``  Read-only exploration / discovery. Default model:
                    ``config.model.fast`` — token-cheap because the
                    work is mostly grep / read / report.
    ``debugger``    Deep-reasoning bug investigation. Default model:
                    ``config.model.strong``.
    ``reviewer``    Read-only critique of proposed changes. Default
                    model: ``config.model.strong``.

Each role's system prompt is fixed in this module. Users can re-route
a role to a different model via the ``[subagents.<role>]`` block in
``config.toml`` — see :class:`quoriv.config.schema.SubAgentsConfig`.

Model resolution turns the config token (``"default"`` / ``"fast"`` /
``"strong"`` / a literal ``"provider:name"``) into a built model
instance via :func:`quoriv.models.factory.get_model`. Going through
Quoriv's factory rather than letting DeepAgents call
``init_chat_model`` directly keeps the keychain-aware key lookup
consistent across the main agent and all subagents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from quoriv.models import get_model

if TYPE_CHECKING:
    from deepagents import SubAgent

    from quoriv.config import QuorivConfig


@dataclass(frozen=True, slots=True)
class _SubAgentSpec:
    """Static definition of one built-in subagent role.

    ``model_lookup`` is the function that derives the role's default
    model token from a :class:`QuorivConfig` — used as the fallback
    when the user's config doesn't override the model.
    """

    name: str
    description: str
    system_prompt: str


RESEARCHER_PROMPT = """\
You are a read-only research subagent.

Your job is to gather context for the main agent: locate files,
search for symbols / references, read source, summarize what you
find. You may use any read-only tool (``ls``, ``read_file``,
``glob``, ``grep``, ``find_symbol``, ``find_references``,
``go_to_definition``, git read tools). Do not write or edit files;
do not run the shell. If asked to do something outside read-only
scope, refuse and explain why.

Return a focused, factual report. Prefer short, well-organized
notes over long prose. Quote file paths and line numbers when
relevant.
"""

DEBUGGER_PROMPT = """\
You are a debugger subagent.

Your job is to isolate the root cause of a bug. You have access to
the full toolset (read, edit, shell). Approach the problem with
the scientific method: form a hypothesis, design a minimal
experiment, run it, update your mental model, repeat. Prefer
small, reversible probes (print statements, focused unit tests)
over large rewrites.

Report back with: the root cause, the smallest fix that addresses
it, and any follow-up risks. Do not commit changes — leave that
to the main agent or the user.
"""

REVIEWER_PROMPT = """\
You are a read-only code-review subagent.

Your job is to critique proposed changes the main agent (or the
user) has made. Look for: correctness bugs, edge cases that aren't
covered by tests, subtle security issues, style inconsistencies
with the rest of the codebase, missing documentation, places
where the change might break unrelated callers.

You may use any read-only tool to verify claims. Do not edit
files or run the shell. Return a structured review: each finding
gets a one-line summary, a severity (blocker / major / minor /
nit), and a pointer to the relevant file:line.
"""


_BUILTIN_SPECS: dict[str, _SubAgentSpec] = {
    "researcher": _SubAgentSpec(
        name="researcher",
        description=(
            "Read-only research subagent. Use to gather context: locate code, "
            "search for symbols, summarize files. Cannot write or run shell."
        ),
        system_prompt=RESEARCHER_PROMPT,
    ),
    "debugger": _SubAgentSpec(
        name="debugger",
        description=(
            "Deep-reasoning debugger subagent. Use for hard bug investigation "
            "where the scientific method matters more than fast iteration. Has "
            "full tool access."
        ),
        system_prompt=DEBUGGER_PROMPT,
    ),
    "reviewer": _SubAgentSpec(
        name="reviewer",
        description=(
            "Read-only code-review subagent. Use to critique a proposed change "
            "before committing. Returns severity-tagged findings."
        ),
        system_prompt=REVIEWER_PROMPT,
    ),
}
"""Static specs for the three built-in roles, keyed by role name."""


def _resolve_model_token(token: str, config: QuorivConfig) -> str:
    """Turn a config token into a fully-qualified ``provider:name`` id.

    ``"default"`` / ``"fast"`` / ``"strong"`` resolve through the
    ``[model]`` section. Any other value is treated as a literal id
    and returned unchanged — the user is opting out of the
    config-driven routing.
    """
    if token == "default":
        return config.model.default
    if token == "fast":
        return config.model.fast
    if token == "strong":
        return config.model.strong
    return token


def build_subagents(config: QuorivConfig) -> list[SubAgent]:
    """Return the list of :class:`SubAgent` specs for ``create_deep_agent``.

    Resolves each role's configured model token to an actual model
    instance via :func:`quoriv.models.factory.get_model` so subagents
    share Quoriv's keychain-aware key lookup with the main agent.

    Args:
        config: Loaded Quoriv configuration. The ``subagents`` and
            ``model`` sections drive routing.

    Returns:
        A list of DeepAgents :class:`SubAgent` ``TypedDict`` values
        ready to pass to ``create_deep_agent(subagents=...)``.
    """
    role_configs = {
        "researcher": config.subagents.researcher,
        "debugger": config.subagents.debugger,
        "reviewer": config.subagents.reviewer,
    }
    out: list[SubAgent] = []
    for role_name, spec in _BUILTIN_SPECS.items():
        role_config = role_configs[role_name]
        model_id = _resolve_model_token(role_config.model, config)
        # ``cast`` because dict literals don't auto-narrow to a
        # ``TypedDict`` at type-check time — but the shape is right.
        out.append(
            cast(
                "SubAgent",
                {
                    "name": spec.name,
                    "description": spec.description,
                    "system_prompt": spec.system_prompt,
                    "model": get_model(model_id),
                },
            )
        )
    return out
