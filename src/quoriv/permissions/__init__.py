"""Permission mode translation layer.

Quoriv exposes a 4-mode permission posture (``read-only`` / ``ask`` /
``auto`` / ``yolo``) to users. This package translates those modes into
DeepAgents' two underlying mechanisms:

    permissions=[FilesystemPermission(...)]    enforced by FilesystemMiddleware
    interrupt_on={"edit_file": True, ...}      enforced by HumanInTheLoopMiddleware

This is **not** a tool-call guard layer — ``FilesystemMiddleware`` does the
actual gating. Quoriv just compiles modes down to its config dicts.

Modules (implemented in Phase 1):
    modes       4-mode -> (permissions list, interrupt_on dict) translator.
    paths       Always-on path protection rules (``.env``, ``.git/``,
                ``.ssh/``, ``secrets/``) prepended to every mode's permission
                list. Cannot be disabled via configuration.

What's **not** here, and why:

    - No ``guard.py`` — DeepAgents' ``FilesystemMiddleware`` enforces rules
      at the tool level.
    - No ``allowlist.py`` (yet) — Phase 2 UX layer that lets users promote
      a one-time approval to a persistent ``interrupt_on`` exception.
"""
