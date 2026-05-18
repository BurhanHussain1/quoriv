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
from typing import TYPE_CHECKING, Any, cast

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.memory import MemorySaver

from quoriv.core.memory import resolve_memory_files
from quoriv.core.subagents import build_subagents
from quoriv.models import get_model, with_fallbacks
from quoriv.permissions import (
    PATH_PROTECTION,
    PathProtectionMiddleware,
    PermissionMode,
    interrupt_on_for_mode,
)
from quoriv.plugins import discover_plugin_tools
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
    extra_tools: list[Any] | None = None,
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
        extra_tools: Additional tools to append to the agent's tool list,
            after ``QUORIV_TOOLS`` and the entry-point plugin tools.
            Phase 2 Slice 6 uses this for MCP-discovered tools — they're
            loaded asynchronously in :func:`quoriv.app.run_chat` before
            ``build_agent`` is called (which stays sync).

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
    primary_model = get_model(model_id)
    # Phase 3 Slice 9: if the user configured ``[model].fallbacks``,
    # wrap the primary with LangChain's ``with_fallbacks`` so a
    # transient failure on the primary (rate limit, 5xx, network
    # error) automatically rolls over to the next id in the list.
    # Fallbacks that fail to build are logged and skipped — never
    # block agent startup.
    # ``with_fallbacks`` may return a ``RunnableWithFallbacks`` (not a
    # ``BaseChatModel``) when fallbacks are configured, but DeepAgents'
    # ``model=`` parameter accepts any LangChain runnable at runtime.
    # The cast keeps mypy quiet without weakening the public typing of
    # ``with_fallbacks``.
    model = cast("Any", with_fallbacks(primary_model, config.model.fallbacks))
    root = cwd if cwd is not None else Path.cwd()

    backend = LocalShellBackend(root_dir=str(root), virtual_mode=True)
    interrupt_on = interrupt_on_for_mode(mode)
    # Phase 2 Slice 1: hand DeepAgents the existing memory files so its
    # ``MemoryMiddleware`` actually loads them into the system prompt.
    # ``None`` (not an empty list) means "no memory middleware" — that's
    # the contract DeepAgents documents for the ``memory=`` kwarg.
    memory_files = [str(p) for p in resolve_memory_files(root)]
    # Phase 2 Slice 4: register Quoriv's built-in subagents (researcher /
    # debugger / reviewer) so the main agent can delegate via the
    # ``task`` tool. Each role's model is resolved from the
    # ``[subagents.*]`` block in config.
    subagents = build_subagents(config)
    # Phase 2 Slice 5: discover third-party tools registered via the
    # ``quoriv.plugins`` entry-point group and merge them after
    # ``QUORIV_TOOLS``. Disabled plugins are skipped. Broken plugins
    # are logged and dropped — they never break a session.
    plugin_tools = discover_plugin_tools(disabled=config.plugins.disabled)
    # Phase 2 Slice 6: caller-supplied extras (typically MCP tools
    # loaded via ``quoriv.plugins.mcp.load_mcp_tools`` from the async
    # chat loop). Append last so user-facing tools shadow built-ins
    # only by explicit name — handy if users want to override one.
    extras = list(extra_tools) if extra_tools else []

    return create_deep_agent(
        model=model,
        backend=backend,
        tools=[*QUORIV_TOOLS, *plugin_tools, *extras],
        middleware=[PathProtectionMiddleware(list(PATH_PROTECTION))],
        checkpointer=checkpointer if checkpointer is not None else MemorySaver(),
        interrupt_on=interrupt_on or None,
        memory=memory_files or None,
        subagents=subagents,
    )
