"""Entry-point-driven plugin loader — Phase 2 Slice 5.

Third-party packages register tools by declaring an entry point under
the ``quoriv.plugins`` group in their ``pyproject.toml``::

    [project.entry-points."quoriv.plugins"]
    my_plugin = "my_pkg:plugin_factory"

The named callable (``my_pkg.plugin_factory`` here) takes no arguments
and returns an iterable of LangChain ``BaseTool`` instances — typically
``@tool``-decorated functions. The loader is called from
:func:`quoriv.core.agent.build_agent` at session start and merges the
returned tools into the agent's ``tools=`` list.

The loader is defensive on purpose. A broken plugin (import error,
factory raises, factory returns a non-iterable) is logged via
:mod:`loguru` and **skipped** rather than failing the session — users
should be able to start a chat even if one plugin's tree is currently
busted.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from langchain_core.tools import BaseTool


QUORIV_PLUGINS_GROUP = "quoriv.plugins"
"""Setuptools entry-point group name plugins register under."""


@dataclass(frozen=True, slots=True)
class PluginRecord:
    """One discovered plugin's identity + load outcome.

    Used by ``/tools`` (and a future ``/plugins`` slash command) to
    render the set of plugins the session sees.
    """

    name: str
    value: str  # the "pkg.module:attr" entry-point target
    tool_names: tuple[str, ...]
    error: str | None  # set when load_plugin failed; ``None`` on success


def _list_entry_points() -> list[EntryPoint]:
    """Return entry points registered under the Quoriv plugins group.

    Wraps ``importlib.metadata.entry_points`` so monkeypatching for
    tests is straightforward (set this function's return value rather
    than reaching into ``importlib.metadata``).
    """
    return list(entry_points(group=QUORIV_PLUGINS_GROUP))


def _coerce_tools(value: object, plugin_name: str) -> list[BaseTool]:
    """Validate that ``value`` looks like ``Iterable[BaseTool]``.

    The loader is defensive — a plugin that returns the wrong shape
    gets dropped with a warning rather than crashing the session.
    """
    # ``BaseTool`` is the LangChain abstract; we duck-type by checking
    # for the attributes the agent actually uses (``name`` and
    # ``invoke``). This avoids importing langchain_core eagerly when
    # there are no plugins to load.
    try:
        items = list(value)  # type: ignore[call-overload]
    except TypeError as exc:
        logger.warning(
            "plugin {!r} returned a non-iterable ({}); skipping.",
            plugin_name,
            exc,
        )
        return []
    tools: list[BaseTool] = []
    for item in items:
        if not hasattr(item, "name") or not (hasattr(item, "invoke") or hasattr(item, "ainvoke")):
            logger.warning(
                "plugin {!r} returned a non-tool object ({!r}); skipping.",
                plugin_name,
                item,
            )
            continue
        tools.append(item)
    return tools


def list_plugins() -> list[PluginRecord]:
    """Return one :class:`PluginRecord` per discovered plugin.

    Loads every registered plugin (even ones the user has disabled —
    callers can filter on ``record.name``) and captures whether the
    load succeeded. Used by introspection UI; not by the agent
    builder, which calls :func:`discover_plugin_tools` instead.
    """
    out: list[PluginRecord] = []
    for ep in _list_entry_points():
        try:
            factory = ep.load()
        except Exception as exc:
            out.append(PluginRecord(name=ep.name, value=ep.value, tool_names=(), error=str(exc)))
            continue
        try:
            tools = _coerce_tools(factory(), ep.name)
        except Exception as exc:
            out.append(PluginRecord(name=ep.name, value=ep.value, tool_names=(), error=str(exc)))
            continue
        tool_names = tuple(t.name for t in tools)
        out.append(PluginRecord(name=ep.name, value=ep.value, tool_names=tool_names, error=None))
    return out


def discover_plugin_tools(
    disabled: Iterable[str] | None = None,
) -> list[BaseTool]:
    """Discover and load tools from every enabled plugin.

    Args:
        disabled: Names of plugins to skip. Match the entry-point
            name (the ``my_plugin`` in
            ``my_plugin = "my_pkg:plugin_factory"``).

    Returns:
        Flat list of tools, suitable for concatenation with
        ``QUORIV_TOOLS`` before handing to
        ``create_deep_agent(tools=...)``.
    """
    skip = set(disabled) if disabled is not None else set()
    tools: list[BaseTool] = []
    for ep in _list_entry_points():
        if ep.name in skip:
            logger.debug("plugin {!r} disabled by config — skipping.", ep.name)
            continue
        try:
            factory = ep.load()
        except Exception as exc:
            logger.warning("plugin {!r} failed to import ({}); skipping.", ep.name, exc)
            continue
        try:
            produced = factory()
        except Exception as exc:
            logger.warning("plugin {!r} factory raised ({}); skipping.", ep.name, exc)
            continue
        tools.extend(_coerce_tools(produced, ep.name))
    return tools
