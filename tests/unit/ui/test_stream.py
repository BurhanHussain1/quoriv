"""Tests for `quoriv.ui.stream`.

The Rich ``Live`` mechanics are integration-territory; here we verify the
plain state-management invariants (buffer accumulation, finalize semantics).
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from quoriv.ui.stream import StreamRenderer


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    # force_terminal=False keeps Live in a quiet mode that doesn't try to
    # do cursor tricks against the StringIO.
    console = Console(file=buf, width=80, force_terminal=False, no_color=True)
    return console, buf


class TestStreamRenderer:
    def test_initial_state_idle(self) -> None:
        console, _ = _make_console()
        r = StreamRenderer(console)
        assert r.is_streaming is False
        assert r.buffer == ""

    def test_empty_push_is_noop(self) -> None:
        console, _ = _make_console()
        r = StreamRenderer(console)
        r.push("")
        assert r.is_streaming is False
        assert r.buffer == ""

    def test_single_push_accumulates(self) -> None:
        console, _ = _make_console()
        r = StreamRenderer(console)
        r.push("hello")
        assert r.buffer == "hello"
        r.finalize()

    def test_multiple_pushes_accumulate(self) -> None:
        console, _ = _make_console()
        r = StreamRenderer(console)
        r.push("hello ")
        r.push("**world**")
        assert r.buffer == "hello **world**"
        r.finalize()

    def test_finalize_returns_full_text_and_resets(self) -> None:
        console, _ = _make_console()
        r = StreamRenderer(console)
        r.push("alpha")
        r.push(" beta")
        text = r.finalize()
        assert text == "alpha beta"
        assert r.buffer == ""
        assert r.is_streaming is False

    def test_finalize_on_idle_returns_empty(self) -> None:
        console, _ = _make_console()
        r = StreamRenderer(console)
        assert r.finalize() == ""

    def test_can_restart_after_finalize(self) -> None:
        console, _ = _make_console()
        r = StreamRenderer(console)
        r.push("first")
        assert r.finalize() == "first"
        r.push("second")
        assert r.finalize() == "second"
