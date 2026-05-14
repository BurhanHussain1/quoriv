"""Permission mode translation + path-protection guard.

Quoriv exposes a 4-mode permission posture (``read-only`` / ``ask`` /
``auto`` / ``yolo``) to users. This package compiles those modes into
DeepAgents config and enforces always-on path protection.

Two layers:

    permissions=[FilesystemPermission(...)]    (intent — see ``paths.py``)
    interrupt_on={"edit_file": True, ...}      pause-for-approval
    PathProtectionMiddleware                   hard tool-call denial

DeepAgents 0.6.1 doesn't accept ``permissions=`` alongside sandbox
backends, so we enforce path protection via the local
:class:`PathProtectionMiddleware` instead. ``interrupt_on`` is still
DeepAgents' own mechanism.

Modules:
    modes       4-mode -> ``interrupt_on`` dict translator. Defines
                ``WRITE_TOOLS`` and ``SHELL_TOOLS`` frozensets and the
                ``PermissionMode`` Literal type.
    paths       ``PATH_PROTECTION`` — tuple of always-on deny rules for
                ``.env*`` / ``.git/`` / ``.ssh/`` / ``secrets/``.
    guard       ``PathProtectionMiddleware`` — the actual enforcement
                layer. Plugged into ``create_deep_agent(middleware=...)``
                by :func:`quoriv.core.agent.build_agent`.

What's **not** here, and why:

    - No ``allowlist.py`` (yet) — Phase 2 UX layer for "always allow"
      promotion of one-off approvals to persistent ``interrupt_on``
      exceptions.
"""

from __future__ import annotations

from quoriv.permissions.guard import PathProtectionMiddleware
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
    "PathProtectionMiddleware",
    "PermissionMode",
    "interrupt_on_for_mode",
    "is_read_only",
]
