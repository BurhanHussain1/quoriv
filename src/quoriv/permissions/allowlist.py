"""Session-scoped tool allowlist — Phase 2 Slice 3.

A :class:`SessionAllowlist` records tools the user has explicitly
promoted from a one-time HITL approval ("approve") to a persistent
one ("approve always"). It is a UX layer on top of DeepAgents'
``interrupt_on=`` mechanism — the underlying agent still receives a
plain "approve" decision; Quoriv just skips the user-facing prompt
for tools the user has already greenlit for this session.

The allowlist lives in memory for the lifetime of a chat session
(one ``run_chat`` invocation). It is intentionally *not* persisted
across restarts — re-prompting on a new session keeps the user in
control of what's auto-approved.

Granularity: keyed by tool name (``"execute"``, ``"write_file"``,
``"edit_file"``, …). A future slice may refine this to tool-name +
argument-shape, but tool-name matches users' mental model ("always
allow shell" / "always allow file writes") and matches the
granularity ``interrupt_on=`` itself uses.
"""

from __future__ import annotations


class SessionAllowlist:
    """Mutable set of tool names auto-approved for the current session.

    Designed to be created once per chat session in
    :func:`quoriv.app._interactive_loop` and threaded through the
    HITL decision pipeline. ``in`` checks return ``True`` for tools
    the user has previously promoted via ``approve_always``.
    """

    __slots__ = ("_tools",)

    def __init__(self) -> None:
        self._tools: set[str] = set()

    def allow(self, tool_name: str) -> None:
        """Promote ``tool_name`` to auto-approve for the rest of the session.

        Idempotent — adding a name that's already on the list is a
        no-op rather than an error.
        """
        self._tools.add(tool_name)

    def __contains__(self, tool_name: object) -> bool:
        # Accept ``object`` so ``"foo" in allowlist`` works for any
        # comparable type without mypy complaints at call sites.
        if not isinstance(tool_name, str):
            return False
        return tool_name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def tools(self) -> frozenset[str]:
        """Return an immutable snapshot of the allowlisted tool names."""
        return frozenset(self._tools)

    def clear(self) -> None:
        """Drop every allowlist entry — used by ``/clear`` to reset state."""
        self._tools.clear()
