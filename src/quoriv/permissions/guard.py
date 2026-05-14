"""Custom guard middleware enforcing :data:`PATH_PROTECTION`.

DeepAgents 0.6.1 raises ``NotImplementedError`` if you pass
``permissions=`` to ``create_deep_agent`` alongside a backend that
implements ``SandboxBackendProtocol`` (which ``LocalShellBackend``
does — and we need ``LocalShellBackend`` so the agent can run shell
commands). To enforce path protection *without* giving up shell
execution, we run our own ``AgentMiddleware`` here.

How it works:

    1. ``after_model`` runs immediately after the LLM emits an
       ``AIMessage`` and before any tool actually executes.
    2. We scan the AIMessage's ``tool_calls`` for filesystem-touching
       tools (read/write/edit/ls/glob/grep).
    3. For each one, we extract the target path and check it against
       the configured :class:`FilesystemPermission` rules using the same
       wcmatch globbing DeepAgents itself uses internally.
    4. If a deny rule matches, we drop that tool call from the AIMessage
       and append a synthetic error ``ToolMessage`` in its place. The
       agent sees the error on the next turn and adapts.

This middleware should be passed via ``middleware=[...]`` to
``create_deep_agent``, *before* ``HumanInTheLoopMiddleware`` runs.
The DeepAgents middleware-stack ordering puts user middleware ahead of
HITL, so a denied tool call never reaches the approval prompt — it's
hard-rejected.

When upstream DeepAgents/LangChain ships native ``permissions=`` with
sandbox backends, this module can be retired.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wcmatch.glob as wcglob
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from deepagents import FilesystemPermission
    from langchain.agents import AgentState
    from langgraph.runtime import Runtime


_WCMATCH_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR
"""Match DeepAgents' own ``FilesystemMiddleware`` glob semantics."""


_TOOL_OPERATION: dict[str, str] = {
    "ls": "read",
    "read_file": "read",
    "glob": "read",
    "grep": "read",
    "write_file": "write",
    "edit_file": "write",
}
"""Map built-in DeepAgents tool names to their filesystem operation kind.

If the name isn't in this map, the tool is treated as path-irrelevant
and the middleware lets it through.
"""


def _check_denial(
    rules: Sequence[FilesystemPermission],
    operation: str,
    path: str,
) -> FilesystemPermission | None:
    """Return the first matching deny rule, or ``None`` if allowed.

    Iterates rules in declaration order; the first deny that matches the
    operation + path wins. Allow rules and non-matching rules are
    skipped.
    """
    for rule in rules:
        if operation not in rule.operations:
            continue
        if rule.mode != "deny":
            continue
        if any(wcglob.globmatch(path, pattern, flags=_WCMATCH_FLAGS) for pattern in rule.paths):
            return rule
    return None


def _denial_message(rule: FilesystemPermission, path: str, operation: str) -> str:
    """The message returned to the agent when a tool call is blocked."""
    return (
        f"Quoriv path-protection: {operation} denied for {path!r} "
        f"(matches deny rule for {rule.paths!r}). This path is protected "
        f"and cannot be modified by the agent. Pick a different path or "
        f"ask the user to handle this file manually."
    )


def _extract_path(args: object) -> str | None:
    """Pull the target path out of a tool call's args dict.

    DeepAgents file tools use ``file_path`` or ``path`` depending on
    the operation. We check both.
    """
    if not isinstance(args, dict):
        return None
    candidate = args.get("file_path") or args.get("path")
    return candidate if isinstance(candidate, str) else None


class PathProtectionMiddleware(AgentMiddleware):
    """Reject file tool calls that target paths in the deny list.

    Runs in ``after_model`` so it inspects the AIMessage's
    ``tool_calls`` before any tool actually executes. Denied calls are
    swapped out for synthetic error ``ToolMessage`` objects; the agent
    sees those on its next turn.

    Args:
        rules: A sequence of :class:`FilesystemPermission` objects.
            Allow rules are ignored (only deny rules matter here); the
            absence of a matching deny means "allowed".
    """

    def __init__(self, rules: Sequence[FilesystemPermission]) -> None:
        super().__init__()
        self._rules = list(rules)

    @property
    def rules(self) -> list[FilesystemPermission]:
        """The configured deny rules (read-only view)."""
        return list(self._rules)

    def after_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],  # part of the AgentMiddleware contract
    ) -> dict[str, Any] | None:
        """Replace denied tool calls with error ``ToolMessage`` objects."""
        messages = state.get("messages", [])
        last_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)),
            None,
        )
        if last_ai is None or not last_ai.tool_calls:
            return None

        kept_tool_calls: list[Any] = []
        error_messages: list[ToolMessage] = []
        modified = False

        for tool_call in last_ai.tool_calls:
            operation = _TOOL_OPERATION.get(tool_call["name"])
            if operation is None:
                kept_tool_calls.append(tool_call)
                continue

            path = _extract_path(tool_call.get("args"))
            if path is None:
                kept_tool_calls.append(tool_call)
                continue

            rule = _check_denial(self._rules, operation, path)
            if rule is None:
                kept_tool_calls.append(tool_call)
                continue

            modified = True
            error_messages.append(
                ToolMessage(
                    content=_denial_message(rule, path, operation),
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                    status="error",
                )
            )

        if not modified:
            return None

        last_ai.tool_calls = kept_tool_calls
        return {"messages": [last_ai, *error_messages]}

    async def aafter_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Async hook — delegates to the sync implementation."""
        return self.after_model(state, runtime)
