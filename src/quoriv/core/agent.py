"""Build a Quoriv-configured DeepAgent for a chat session.

This is the seam between Quoriv (config, CLI, UI, Quoriv-specific tools)
and DeepAgents (the agent runtime). Day 5 wires the minimum needed for an
end-to-end loop:

    * The user's chosen model (built by ``quoriv.models.get_model``).
    * ``LocalShellBackend`` rooted at the session's working directory —
      gives the agent real file ops + a real shell. ``virtual_mode=True``
      keeps tool-visible paths sandboxed to POSIX paths under ``root_dir``.
    * An in-memory checkpointer so conversation state survives across
      turns within a session.

**Day 5 limitation — path protection deferred to Phase 1.** DeepAgents
0.6.1 rejects passing ``permissions=`` when the backend implements
``SandboxBackendProtocol`` (which ``LocalShellBackend`` does), because
tool-level permissions for the ``execute`` tool are not yet implemented
upstream. Since Day 5 must have ``execute`` available for end-to-end
demos, we leave ``permissions=`` unset for now. The ``PATH_PROTECTION``
constant remains defined here as the policy we want — Phase 1 will
enforce it via a different mechanism (custom guard middleware, or
``interrupt_on`` for write/edit tools mapped from the permission mode).

Phase 1 will also translate Quoriv's permission modes into DeepAgents'
``interrupt_on=`` config, add Quoriv-specific tools (AST, git, tests,
web, MCP), load memory files from ``PROJECT.md`` / ``~/.quoriv/memory.md``,
and swap the in-memory checkpointer for a ``SqliteSaver`` so sessions
persist across restarts.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.memory import MemorySaver

from quoriv.models import get_model

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from quoriv.config import QuorivConfig


PATH_PROTECTION: tuple[FilesystemPermission, ...] = (
    FilesystemPermission(operations=["write"], paths=["/.env"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/.env.*"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/.git/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/.ssh/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/secrets/**"], mode="deny"),
)
"""Always-on path protection rules.

Defined here as the policy intent for Phase 1. **Not currently passed to
DeepAgents** (see module docstring for the upstream incompatibility with
sandbox backends in 0.6.1). Phase 1 will wire them in via a different
enforcement layer.

The intent: deny writes to ``.env``/``.env.*``, anything under ``.git/``,
and both reads and writes under ``.ssh/`` and ``secrets/``. Paths are
POSIX-style relative to the backend's ``root_dir`` (the session's
working directory).
"""


def build_agent(
    config: QuorivConfig,
    *,
    model_override: str | None = None,
    cwd: Path | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> Any:  # create_deep_agent's deeply generic return type isn't worth pinning
    """Construct a configured DeepAgent for a chat session.

    Args:
        config: Loaded Quoriv configuration.
        model_override: Optional ``provider:name`` string overriding
            ``config.model.default`` for this session.
        cwd: Working directory the agent's filesystem and shell are rooted
            in. Defaults to ``Path.cwd()``.
        checkpointer: Optional LangGraph checkpointer. Defaults to a fresh
            in-memory ``MemorySaver`` so multi-turn state persists within
            the session.

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

    return create_deep_agent(
        model=model,
        backend=backend,
        checkpointer=checkpointer if checkpointer is not None else MemorySaver(),
    )
