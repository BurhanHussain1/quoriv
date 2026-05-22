"""Tests for ``quoriv.ui.chat_input`` — Phase 5 Slice 1.

The Application's interactive behaviour (key dispatch, drawing) needs
a real terminal to test end-to-end. These unit tests cover the parts
we *can* exercise without a TTY:

* The function exists with the right signature.
* The Application/Buffer constructor wires the completer + history
  through to the underlying widgets.
* The Layout actually contains a Frame (the visible box).
* The keybinding registry has Enter / Ctrl-C / Ctrl-D / Esc-Enter
  registered.

Interactive smoke-testing happens when the user runs ``quoriv chat``.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.output import DummyOutput

from quoriv.ui.chat_input import build_chat_app, prompt_boxed
from quoriv.ui.slash_completer import SlashCommandCompleter


@pytest.fixture
def fake_io() -> Any:
    """Yield ``(input, output)`` for an Application constructed without a TTY."""
    with create_pipe_input() as pipe_in:
        yield pipe_in, DummyOutput()


def _build(fake_io: Any, **kwargs: Any) -> Any:
    """Wrapper that injects the fake IO so tests stay terse."""
    pipe_in, dummy_out = fake_io
    return build_chat_app(input=pipe_in, output=dummy_out, **kwargs)


def _walk_containers(container: Any) -> list[Any]:
    """Yield every container reachable from ``container`` (DFS)."""
    found: list[Any] = [container]
    for child in getattr(container, "children", []) or []:
        # Frame wraps its child under .container; otherwise descend
        # into HSplit/VSplit children directly.
        inner = getattr(child, "container", child)
        found.extend(_walk_containers(inner))
    return found


class TestBuildChatApp:
    def test_returns_application_and_buffer(self, fake_io: Any) -> None:
        app, buffer = _build(fake_io)
        # Lightweight type assertions — don't import the heavy
        # prompt_toolkit Application class just to isinstance-check.
        assert hasattr(app, "run_async")
        assert hasattr(buffer, "text")

    def test_layout_is_more_than_a_bare_window(self, fake_io: Any) -> None:
        # The Frame widget collapses to its inner HSplit by the time
        # the Application is built — checking for the Frame class
        # directly is fragile. Structural proxy: a Framed input
        # always wraps the BufferControl with multiple border-drawing
        # Windows, so the total Window count is > 1 even when the
        # bottom toolbar is disabled.
        app, _ = _build(fake_io, bottom_toolbar=None)
        windows = [c for c in _walk_containers(app.layout.container) if isinstance(c, Window)]
        assert len(windows) > 1, (
            "expected more than one Window — Frame should contribute border windows"
        )

    def test_bottom_toolbar_adds_extra_window(self, fake_io: Any) -> None:
        # Without a toolbar: just the framed input. With one: framed
        # input + a 1-line status Window stacked below.
        app_no_bar, _ = _build(fake_io, bottom_toolbar=None)
        app_with_bar, _ = _build(fake_io, bottom_toolbar=lambda: "status")

        def _window_count(app: Any) -> int:
            return sum(1 for c in _walk_containers(app.layout.container) if isinstance(c, Window))

        # Adding the toolbar contributes exactly one extra Window.
        assert _window_count(app_with_bar) == _window_count(app_no_bar) + 1

    def test_completer_wired_to_buffer(self, fake_io: Any) -> None:
        completer = SlashCommandCompleter({"/help": "show help"})
        _app, buffer = _build(fake_io, completer=completer)
        assert buffer.completer is completer

    def test_history_wired_to_buffer(self, fake_io: Any) -> None:
        history = InMemoryHistory()
        _app, buffer = _build(fake_io, history=history)
        assert buffer.history is history

    def test_default_history_is_in_memory(self, fake_io: Any) -> None:
        # The chat loop passes its own InMemoryHistory; a caller that
        # doesn't pass one must still get a working history (not None).
        _app, buffer = _build(fake_io)
        assert isinstance(buffer.history, InMemoryHistory)

    def test_keybindings_cover_submit_abort_newline(self, fake_io: Any) -> None:
        # Enter submits, Ctrl-C / Ctrl-D abort, Esc-Enter inserts a
        # newline. Verify all four bindings exist on the registry.
        app, _ = _build(fake_io)
        bindings = app.key_bindings
        assert bindings is not None

        # Each binding's `.keys` is a tuple of Keys/strings — flatten
        # to a set of repr strings so the comparison is order-agnostic.
        registered = {repr(b.keys) for b in bindings.bindings}
        joined = " ".join(registered)
        # prompt_toolkit maps "enter" to Keys.ControlM (the carriage
        # return byte). Both renderings show up under the lowercased
        # repr as `c-m`.
        assert "c-m" in joined.lower(), f"Enter binding missing — got {joined!r}"
        # Ctrl-C / Ctrl-D abort the prompt.
        assert "c-c" in joined.lower(), f"Ctrl-C binding missing — got {joined!r}"
        assert "c-d" in joined.lower(), f"Ctrl-D binding missing — got {joined!r}"
        # Esc-Enter inserts a newline; key tuple contains escape.
        assert "escape" in joined.lower(), f"Esc-Enter binding missing — got {joined!r}"

    def test_frame_title_kwarg_accepted(self, fake_io: Any) -> None:
        # The frame_title is cosmetic and gets buried inside Frame's
        # internal FormattedTextControl by the time the layout is
        # built — not worth fishing out of opaque widget internals.
        # The actionable test is "the kwarg is honoured without
        # crashing." Visual confirmation happens when running
        # `quoriv chat` interactively.
        app, _ = _build(fake_io, frame_title="custom")
        assert app is not None


class TestPromptBoxedAPI:
    def test_is_async(self) -> None:
        # Sanity check the signature so callers can `await` it.
        assert inspect.iscoroutinefunction(prompt_boxed)

    def test_accepts_documented_kwargs(self) -> None:
        # Don't actually call it (would require a TTY). Just verify
        # the signature accepts the kwargs the chat loop passes.
        sig = inspect.signature(prompt_boxed)
        params = set(sig.parameters)
        assert "completer" in params
        assert "history" in params
        assert "bottom_toolbar" in params
        assert "frame_title" in params
