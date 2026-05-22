"""Bordered-frame chat input — Phase 5 Slices 1 and 2.

Two distinct shapes of prompt_toolkit Application live here:

* :func:`build_chat_app` / :func:`prompt_boxed` build a **one-shot**
  Application that handles a single input turn (the Slice 1 design).
  Kept because unit tests use it to verify layout / keybindings
  without spinning up the full persistent UI, and because callers
  outside the chat loop (e.g. a future ``quoriv ask`` mode) might
  want a single bordered prompt.
* :class:`ChatApp` (re-exported from :mod:`quoriv.ui.chat_app`) is
  the **persistent** Application that owns the chat session: input
  buffer, streamed-response window, status toolbar, and overlay
  Floats for HITL approval modals. This is what
  :func:`quoriv.app.run_chat` drives in v1.2.0.

Implementation notes for the one-shot helpers:

* ``Ctrl+C`` / ``Ctrl+D`` raise :class:`EOFError` so the existing
  loop's exception handling in ``app._interactive_loop`` keeps
  working unchanged.
* ``Enter`` submits the current buffer; ``Esc-Enter`` (Alt+Enter on
  most terminals) inserts a newline for multi-line composition.
* The full :class:`prompt_toolkit.history.History` interface is
  honoured — pass a shared ``InMemoryHistory`` (or
  ``FileHistory(.quoriv/history)``) across turns to keep arrow-key
  navigation working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.history import History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.widgets import Frame

from quoriv.ui.chat_app import ChatApp

if TYPE_CHECKING:
    from collections.abc import Callable

    from prompt_toolkit.completion import Completer

__all__ = ["ChatApp", "build_chat_app", "prompt_boxed"]


def build_chat_app(
    *,
    completer: Completer | None = None,
    history: History | None = None,
    bottom_toolbar: Callable[[], str] | None = None,
    frame_title: str = "quoriv",
    output: Any = None,
    input: Any = None,
) -> tuple[Application[str], Buffer]:
    """Construct the Application + Buffer for one chat-input turn.

    Exposed separately from :func:`prompt_boxed` so unit tests can
    introspect the layout / keybindings without spawning a real
    terminal.

    Args:
        completer: Optional slash-command completer. ``None`` disables
            the popup.
        history: Optional input history. Defaults to a fresh
            ``InMemoryHistory`` per call when omitted — the chat loop
            passes a shared instance so arrow-key recall survives
            between turns.
        bottom_toolbar: Zero-arg callable returning the status text
            shown below the input frame. ``None`` hides the toolbar.
        frame_title: Label shown in the top-left corner of the
            bordered frame.

    Returns:
        ``(app, buffer)`` — the Application configured for one input
        turn and the underlying Buffer the user types into.
    """
    buffer = Buffer(
        completer=completer,
        history=history if history is not None else InMemoryHistory(),
        multiline=False,
        complete_while_typing=True,
    )

    kb = KeyBindings()

    @kb.add("enter")
    def _submit(event: Any) -> None:
        event.app.exit(result=buffer.text)

    @kb.add("c-c")
    @kb.add("c-d")
    def _abort(event: Any) -> None:
        # Surface the same exception PromptSession raises so the
        # existing chat loop's exit path keeps working.
        event.app.exit(exception=EOFError())

    @kb.add("escape", "enter")
    def _newline(event: Any) -> None:
        # Alt/Esc+Enter inserts a literal newline for multi-line input.
        buffer.insert_text("\n")

    # Build the layout. The Frame draws the visible box; HSplit stacks
    # the input frame above the (optional) status toolbar.
    input_window = Window(BufferControl(buffer=buffer), height=1, wrap_lines=False)
    framed_input = Frame(input_window, title=frame_title)

    children: list[Any] = [framed_input]
    if bottom_toolbar is not None:
        status_window = Window(
            FormattedTextControl(bottom_toolbar),
            height=1,
            style="class:bottom-toolbar",
        )
        children.append(status_window)

    layout = Layout(HSplit(children))
    # ``output`` / ``input`` are passthroughs for tests that need to
    # construct the Application without a real TTY (e.g. by injecting
    # ``DummyOutput`` + ``create_pipe_input()``). Production callers
    # leave them ``None`` so prompt_toolkit auto-detects the terminal.
    app_kwargs: dict[str, Any] = {
        "layout": layout,
        "key_bindings": kb,
        "full_screen": False,
        "mouse_support": False,
    }
    if output is not None:
        app_kwargs["output"] = output
    if input is not None:
        app_kwargs["input"] = input
    app: Application[str] = Application(**app_kwargs)
    return app, buffer


async def prompt_boxed(
    *,
    completer: Completer | None = None,
    history: History | None = None,
    bottom_toolbar: Callable[[], str] | None = None,
    frame_title: str = "quoriv",
) -> str:
    """Run one bordered-input turn and return the submitted text.

    Raises:
        EOFError: When the user pressed Ctrl+C or Ctrl+D. Mirrors
            ``PromptSession.prompt_async`` behaviour so the chat loop
            doesn't need bespoke exception handling.
    """
    app, _buffer = build_chat_app(
        completer=completer,
        history=history,
        bottom_toolbar=bottom_toolbar,
        frame_title=frame_title,
    )
    result = await app.run_async()
    return result if isinstance(result, str) else ""
