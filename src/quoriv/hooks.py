"""Hook registry — Phase 3 Slice 10.

A tiny event bus the chat loop fires during a turn so user-provided
callbacks can observe (and instrument) what the agent is doing.
Designed for telemetry / logging / lightweight policy use cases —
not for *modifying* the agent's behavior. Callbacks see what
happened; they don't change it.

Three events ship today (more can be added without breaking the
registry shape since the dispatch is keyed by event name):

    ``pre_tool``    Fires right before a tool starts running.
                    Kwargs: ``tool_name``, ``args``.
    ``post_tool``   Fires right after a tool finishes.
                    Kwargs: ``tool_name``, ``output``.
    ``on_message``  Fires when the model finishes a streaming
                    response. Kwargs: ``message`` (the AIMessage).

Design notes:

* **Defensive**: a callback that raises is logged via :mod:`loguru`
  and the chat loop continues. One broken hook should never break
  a turn.
* **No magic ordering**: callbacks fire in registration order.
* **Per-session instance**, not a module-level singleton. The chat
  loop constructs one ``HookRegistry`` per ``run_chat`` invocation
  and threads it through. Tests get a fresh instance per case.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable


HookEvent = Literal["pre_tool", "post_tool", "on_message"]
"""Allowed event names. Adding a new event means adding a string
literal here and a ``fire`` call at the right point in
:mod:`quoriv.app`."""


_VALID_EVENTS: frozenset[str] = frozenset({"pre_tool", "post_tool", "on_message"})


class HookRegistry:
    """In-memory event bus for ``pre_tool`` / ``post_tool`` / ``on_message``.

    Callbacks are stored per event in registration order and fired
    sequentially. A callback that raises has its exception logged
    and dropped — the registry never propagates a hook failure to
    the caller.
    """

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = {event: [] for event in _VALID_EVENTS}

    def register(self, event: HookEvent, callback: Callable[..., Any]) -> None:
        """Add ``callback`` to the handlers for ``event``.

        Args:
            event: One of the values in :data:`HookEvent`.
            callback: Any callable matching the event's kwargs.

        Raises:
            ValueError: If ``event`` is not a recognized hook event.
                Caught early so a typo doesn't silently disable
                instrumentation.
        """
        if event not in _VALID_EVENTS:
            raise ValueError(f"Unknown hook event {event!r}. Valid: {sorted(_VALID_EVENTS)}")
        self._handlers[event].append(callback)

    def fire(self, event: HookEvent, **kwargs: Any) -> None:
        """Invoke every callback registered for ``event``.

        Unknown event names are silently ignored — emitters in
        :mod:`quoriv.app` already know which events they fire, so
        a typo there would be a programming error, not user input.
        A callback that raises is logged at warning level and the
        remaining handlers still run.
        """
        for callback in self._handlers.get(event, []):
            try:
                callback(**kwargs)
            except Exception as exc:  # broad on purpose — hooks are user code
                logger.warning("hook {!r} callback raised ({}); continuing.", event, exc)

    def handlers(self, event: HookEvent) -> tuple[Callable[..., Any], ...]:
        """Return an immutable snapshot of the callbacks for ``event``.

        Used by tests and ``/hooks``-style introspection. Returns an
        empty tuple for unknown events rather than raising.
        """
        return tuple(self._handlers.get(event, []))

    def clear(self) -> None:
        """Drop every registered handler — used by tests for isolation."""
        for handlers in self._handlers.values():
            handlers.clear()
