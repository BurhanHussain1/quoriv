"""Tests for `quoriv.ui.stream`.

Phase 5 Slice 2: ``StreamRenderer`` now takes a
:class:`quoriv.ui.chat_app.ChatApp` (or ``None``) rather than a Rich
``Console``. The interactive painting is the persistent Application's
job — these tests cover the state-management invariants (buffer
accumulation, finalize semantics, ChatApp wiring).
"""

from __future__ import annotations

from typing import Any

from quoriv.ui.stream import StreamRenderer


class _FakeChatApp:
    """Minimal stand-in for ChatApp — records every method call.

    Construction is intentionally trivial so the unit tests don't have
    to spin up a real prompt_toolkit Application.
    """

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.finalize_calls = 0
        self.invalidates = 0
        # Mimic the ``app`` attribute the renderer pokes at during
        # sync finalize.
        self.app = self  # so ``chat_app.app.invalidate()`` works

    def push_chunk(self, text: str) -> None:
        self.chunks.append(text)

    async def finalize_stream(self) -> str:
        self.finalize_calls += 1
        return ""

    def invalidate(self) -> None:
        self.invalidates += 1


class TestStreamRenderer:
    def test_initial_state_idle(self) -> None:
        r = StreamRenderer(None)
        assert r.is_streaming is False
        assert r.buffer == ""

    def test_empty_push_is_noop(self) -> None:
        r = StreamRenderer(None)
        r.push("")
        assert r.is_streaming is False
        assert r.buffer == ""

    def test_single_push_accumulates(self) -> None:
        r = StreamRenderer(None)
        r.push("hello")
        assert r.buffer == "hello"

    def test_multiple_pushes_accumulate(self) -> None:
        r = StreamRenderer(None)
        r.push("hello ")
        r.push("**world**")
        assert r.buffer == "hello **world**"

    def test_finalize_returns_full_text_and_resets(self) -> None:
        r = StreamRenderer(None)
        r.push("alpha")
        r.push(" beta")
        text = r.finalize()
        assert text == "alpha beta"
        assert r.buffer == ""
        assert r.is_streaming is False

    def test_finalize_on_idle_returns_empty(self) -> None:
        r = StreamRenderer(None)
        assert r.finalize() == ""

    def test_can_restart_after_finalize(self) -> None:
        r = StreamRenderer(None)
        r.push("first")
        assert r.finalize() == "first"
        r.push("second")
        assert r.finalize() == "second"


class TestStreamRendererWithChatApp:
    def test_push_forwards_to_chat_app(self) -> None:
        fake: Any = _FakeChatApp()
        r = StreamRenderer(fake)
        r.push("hello ")
        r.push("world")
        assert fake.chunks == ["hello ", "world"]
        assert r.buffer == "hello world"

    def test_empty_push_does_not_forward(self) -> None:
        fake: Any = _FakeChatApp()
        r = StreamRenderer(fake)
        r.push("")
        assert fake.chunks == []

    def test_sync_finalize_invalidates_app_and_clears_buffer(self) -> None:
        fake: Any = _FakeChatApp()
        r = StreamRenderer(fake)
        r.push("abc")
        text = r.finalize()
        assert text == "abc"
        assert r.buffer == ""
        # Invalidate is called so the Application repaints with empty
        # stream window on its next natural tick.
        assert fake.invalidates >= 1

    async def test_async_finalize_calls_chat_app_finalize(self) -> None:
        fake: Any = _FakeChatApp()
        r = StreamRenderer(fake)
        r.push("abc")
        text = await r.finalize_async()
        assert text == "abc"
        assert fake.finalize_calls == 1
        assert r.buffer == ""

    async def test_async_finalize_on_idle_skips_chat_app(self) -> None:
        # No buffered content — finalize_async should not call into
        # the ChatApp (no point repainting nothing).
        fake: Any = _FakeChatApp()
        r = StreamRenderer(fake)
        text = await r.finalize_async()
        assert text == ""
        assert fake.finalize_calls == 0
