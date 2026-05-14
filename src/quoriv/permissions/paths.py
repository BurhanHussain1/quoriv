"""Always-on path protection rules.

Canonical location for the policy intent: paths the agent must never
touch (or in some cases never even read), regardless of which permission
mode the user has selected.

**Phase 1 Slice 1 enforcement status.** ``PATH_PROTECTION`` is defined
here as data, but **not yet plumbed into the live agent**. DeepAgents
0.6.1 rejects ``permissions=`` when the backend supports execution
(``LocalShellBackend`` does), so we can't pass these rules through the
standard channel. A custom ``wrap_tool_call`` middleware in a later
Slice will gate write/edit/execute against this list; until then,
protection is provided indirectly by the approval-prompt UI (Slice 2),
where the user can deny any write.

Paths are POSIX-style and rooted at the chat session's working directory
(the backend's ``root_dir``).
"""

from __future__ import annotations

from deepagents import FilesystemPermission

PATH_PROTECTION: tuple[FilesystemPermission, ...] = (
    FilesystemPermission(operations=["write"], paths=["/.env"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/.env.*"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/.git/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/.ssh/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/secrets/**"], mode="deny"),
)
"""Tuple of always-on deny rules.

Intent:
    - Writes blocked: ``/.env``, ``/.env.*``, ``/.git/**``
    - Reads AND writes blocked: ``/.ssh/**``, ``/secrets/**``

Adding new entries here automatically extends protection everywhere the
list is consulted — keep this the single source of truth.
"""
