"""Permission mode translation layer.

Quoriv exposes a 4-mode permission posture (``read-only`` / ``ask`` /
``auto`` / ``yolo``) to users. This package compiles those modes into
DeepAgents' two underlying mechanisms:

    permissions=[FilesystemPermission(...)]    enforced by FilesystemMiddleware
    interrupt_on={"edit_file": True, ...}      enforced by HumanInTheLoopMiddleware

This is **not** a tool-call guard layer — DeepAgents enforces. Quoriv
just emits the config.

Modules:
    modes       4-mode -> ``interrupt_on`` dict translator. Defines
                ``WRITE_TOOLS`` and ``SHELL_TOOLS`` frozensets and the
                ``PermissionMode`` Literal type. Phase 1 Slice 1: only
                ``interrupt_on`` is wired; hard write blocking for
                ``read-only`` is enforced at the approval UI layer.
    paths       ``PATH_PROTECTION`` — tuple of always-on deny rules for
                ``.env*`` / ``.git/`` / ``.ssh/`` / ``secrets/``. Phase 1
                Slice 1b will wire these via a custom ``wrap_tool_call``
                middleware (DeepAgents 0.6.1 doesn't allow passing
                ``permissions=`` alongside sandbox backends).

What's **not** here, and why:

    - No ``guard.py`` — DeepAgents' middleware enforces, not us.
    - No ``allowlist.py`` (yet) — Phase 2 UX layer for "always allow"
      promotion of one-off approvals to persistent ``interrupt_on``
      exceptions.
"""

from __future__ import annotations

from quoriv.permissions.modes import (
    SHELL_TOOLS,
    WRITE_TOOLS,
    PermissionMode,
    interrupt_on_for_mode,
    is_read_only,
)
from quoriv.permissions.paths import PATH_PROTECTION

__all__ = [
    "PATH_PROTECTION",
    "SHELL_TOOLS",
    "WRITE_TOOLS",
    "PermissionMode",
    "interrupt_on_for_mode",
    "is_read_only",
]
