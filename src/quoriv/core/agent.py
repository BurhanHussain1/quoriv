"""Build a Quoriv-configured DeepAgent for a chat session.

This is the seam between Quoriv (config, CLI, UI, Quoriv-specific tools)
and DeepAgents (the agent runtime).

    * The user's chosen model (built by ``quoriv.models.get_model``).
    * ``LocalShellBackend`` rooted at the session's working directory —
      gives the agent real file ops + a real shell. ``virtual_mode=True``
      keeps tool-visible paths sandboxed to POSIX paths under ``root_dir``.
    * An in-memory checkpointer (required for ``interrupt_on``) — Phase 1
      Slice 7 swaps to ``SqliteSaver`` for session persistence.
    * ``interrupt_on=`` derived from the session's permission mode via
      :func:`quoriv.permissions.interrupt_on_for_mode`.
    * :class:`quoriv.permissions.PathProtectionMiddleware` enforcing
      :data:`quoriv.permissions.PATH_PROTECTION` (always-on denylist for
      ``.env*`` / ``.git/`` / ``.ssh/`` / ``secrets/``).

**Why a custom middleware for path protection?** DeepAgents 0.6.1
rejects passing ``permissions=`` when the backend implements
``SandboxBackendProtocol`` (which ``LocalShellBackend`` does). We need
``LocalShellBackend`` so the agent can run shell commands, so we
enforce path protection at the middleware layer instead. See
:mod:`quoriv.permissions.guard` for the mechanics.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.memory import MemorySaver

from quoriv.models import get_model
from quoriv.permissions import (
    PATH_PROTECTION,
    PathProtectionMiddleware,
    PermissionMode,
    interrupt_on_for_mode,
)
from quoriv.tools import QUORIV_TOOLS

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from quoriv.config import QuorivConfig


def build_agent(
    config: QuorivConfig,
    *,
    model_override: str | None = None,
    cwd: Path | None = None,
    mode: PermissionMode = "ask",
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> Any:  # create_deep_agent's deeply generic return type isn't worth pinning
    """Construct a configured DeepAgent for a chat session.

    Args:
        config: Loaded Quoriv configuration.
        model_override: Optional ``provider:name`` string overriding
            ``config.model.default`` for this session.
        cwd: Working directory the agent's filesystem and shell are rooted
            in. Defaults to ``Path.cwd()``.
        mode: Permission mode for the session. Compiled to DeepAgents'
            ``interrupt_on=`` dict via
            :func:`quoriv.permissions.interrupt_on_for_mode`.
        checkpointer: Optional LangGraph checkpointer. Defaults to a fresh
            in-memory ``MemorySaver``. Required for ``interrupt_on`` to
            work, so we always supply at least one.

    Returns:
        The compiled DeepAgent graph. Drive it with
        ``agent.astream_events({"messages": [...]}, config=..., version="v2")``.

    Raises:
        MissingAPIKeyError: If the chosen model's provider has no API key
            configured (env or keychain).
        ValueError: If the model identifier is malformed.
        UnknownProviderError: If the model identifier names an unregistered
            provider.
    """
    model_id = model_override or config.model.default
    model = get_model(model_id)
    root = cwd if cwd is not None else Path.cwd()

    backend = LocalShellBackend(root_dir=str(root), virtual_mode=True)
    interrupt_on = interrupt_on_for_mode(mode)

    return create_deep_agent(
        model=model,
        backend=backend,
        tools=list(QUORIV_TOOLS),
        middleware=[PathProtectionMiddleware(list(PATH_PROTECTION))],
        checkpointer=checkpointer if checkpointer is not None else MemorySaver(),
        interrupt_on=interrupt_on or None,
    )
