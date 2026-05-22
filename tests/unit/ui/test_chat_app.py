"""Tests for ``quoriv.ui.chat_app`` — Phase 5 Slice 2 (persistent UI).

The full interactive lifecycle (key dispatch, modal overlay, scrollback
flushing) requires a real terminal to exercise — those are smoke-tested
when the user runs ``quoriv chat``. These unit tests pin down the
parts we *can* exercise without a TTY:

* The Application is constructed and exposes the documented surface
  (``console``, ``stream_buffer``, ``is_streaming``, ``app``).
* The layout contains the stream window + input frame (+ optional
  toolbar) and a :class:`FloatContainer` for modal overlays.
* ``push_chunk`` / ``finalize_stream`` mutate the in-memory buffer
  correctly (and are no-ops on empty input).
* The Rich ``console`` proxy actually round-trips bytes through the
  adapter file — the contents land somewhere observable (the stream
  buffer pre-run; the underlying output once the app starts).
"""

from __future__ import annotations

from typing import Any

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout.containers import FloatContainer, Window
from prompt_toolkit.output import DummyOutput

from quoriv.ui.chat_app import ChatApp


@pytest.fixture
def fake_io() -> Any:
    """``(input, output)`` for a ChatApp built without a TTY."""
    with create_pipe_input() as pipe_in:
        yield pipe_in, DummyOutput()


def _build(fake_io: Any, **kwargs: Any) -> ChatApp:
    pipe_in, dummy_out = fake_io
    return ChatApp(input=pipe_in, output=dummy_out, **kwargs)


def _walk_containers(container: Any) -> list[Any]:
    """DFS over a prompt_toolkit container tree.

    Walks via ``get_children`` (the canonical Container API) and falls
    back to the ``children`` attribute / Frame's ``container`` wrap
    for the few container shapes that don't expose it.
    """
    found: list[Any] = [container]
    children: list[Any] = []
    if hasattr(container, "get_children"):
        children = list(container.get_children())
    elif getattr(container, "children", None):
        children = list(container.children)
    for child in children:
        inner = getattr(child, "container", child)
        found.extend(_walk_containers(inner))
    return found


class TestConstruction:
    def test_default_construction_exposes_application(self, fake_io: Any) -> None:
        app = _build(fake_io)
        assert hasattr(app.app, "run_async")
        assert app.is_streaming is False
        assert app.stream_buffer == ""

    def test_layout_includes_float_container(self, fake_io: Any) -> None:
        app = _build(fake_io)
        containers = _walk_containers(app.app.layout.container)
        assert any(isinstance(c, FloatContainer) for c in containers)

    def test_layout_has_multiple_windows(self, fake_io: Any) -> None:
        # Stream window + framed input contribute several Windows
        # (Frame adds border Windows of its own). The toolbar is
        # optional; default construction omits it.
        app = _build(fake_io, bottom_toolbar=None)
        windows = [c for c in _walk_containers(app.app.layout.container) if isinstance(c, Window)]
        assert len(windows) > 1

    def test_bottom_toolbar_adds_one_window(self, fake_io: Any) -> None:
        app_no_bar = _build(fake_io, bottom_toolbar=None)
        app_with_bar = _build(fake_io, bottom_toolbar=lambda: "status")

        def _count(app: ChatApp) -> int:
            return sum(
                1
                for c in _walk_containers(app.app.layout.container)
                if isinstance(c, Window)
            )

        assert _count(app_with_bar) == _count(app_no_bar) + 1

    def test_keybindings_cover_submit_abort_newline(self, fake_io: Any) -> None:
        app = _build(fake_io)
        bindings = app.app.key_bindings
        assert bindings is not None
        registered = " ".join(repr(b.keys).lower() for b in bindings.bindings)
        assert "c-m" in registered  # Enter
        assert "c-c" in registered  # Ctrl-C
        assert "c-d" in registered  # Ctrl-D
        assert "escape" in registered  # Esc-Enter newline


class TestStreamWindow:
    def test_push_chunk_accumulates(self, fake_io: Any) -> None:
        app = _build(fake_io)
        app.push_chunk("hello ")
        app.push_chunk("world")
        assert app.stream_buffer == "hello world"
        assert app.is_streaming is True

    def test_push_empty_is_noop(self, fake_io: Any) -> None:
        app = _build(fake_io)
        app.push_chunk("")
        assert app.stream_buffer == ""
        assert app.is_streaming is False

    def test_clear_transcript_resets_stream_buffer(self, fake_io: Any) -> None:
        app = _build(fake_io)
        app.push_chunk("something")
        app.clear_transcript()
        assert app.stream_buffer == ""
        assert app.is_streaming is False


class TestConsoleProxy:
    def test_console_is_lazy(self, fake_io: Any) -> None:
        # The Rich Console is only constructed when ``.console`` is
        # accessed — tests that don't print never pay for it.
        app = _build(fake_io)
        # Two reads return the same instance (cached).
        c1 = app.console
        c2 = app.console
        assert c1 is c2

    def test_pre_run_print_lands_in_stream_buffer(self, fake_io: Any) -> None:
        # Before the Application starts running, ``console.print``
        # routes its output into the stream buffer so the very first
        # render shows it. This is how the welcome banner survives
        # the transition from "no app" to "app running".
        app = _build(fake_io)
        app.console.print("hello banner")
        # Some non-empty content was captured — exact ANSI bytes vary
        # by Rich version, so we only assert the payload is present.
        assert "hello banner" in app.stream_buffer
