"""Streaming markdown renderer for LLM output.

Phase 5 Slice 2 (v1.2.0): the original implementation owned a Rich
``Live`` and repainted markdown chunk-by-chunk. That worked but meant
Rich and prompt_toolkit took turns holding the terminal — Rich during
streaming, prompt_toolkit during input/approval. The split made every
turn boundary look like a "Rich finishes → prompt_toolkit takes over"
flicker.

The renderer is now a thin adapter over :class:`quoriv.ui.chat_app.ChatApp`:

* :meth:`push` forwards each token into the persistent Application's
  stream window — markdown re-renders on every redraw, no Rich Live.
* :meth:`finalize_async` flushes the accumulated text into terminal
  scrollback (via ``run_in_terminal``) and clears the window so the
  next turn starts blank.
* :meth:`finalize` exists for sync callers (tests, shutdown paths)
  that don't have an event loop handy; it returns the accumulated
  text without touching the terminal.

The public surface (``push`` / ``finalize`` / ``buffer`` /
``is_streaming``) mirrors what ``_stream_events`` and the existing
unit tests already use — only the underlying mechanic changes.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quoriv.ui.chat_app import ChatApp


class StreamRenderer:
    """Accumulate streamed tokens and route them into a :class:`ChatApp`."""

    __slots__ = ("_buffer", "_chat_app")

    def __init__(self, chat_app: ChatApp | None) -> None:
        """Build a renderer bound to a persistent chat Application.

        ``chat_app`` is optional so headless contexts (unit tests for
        plain buffer accumulation) can still exercise the renderer
        without spinning up a prompt_toolkit Application. When
        ``None``, ``push`` only updates the in-memory buffer.
        """
        self._chat_app = chat_app
        self._buffer = ""

    @property
    def is_streaming(self) -> bool:
        """True if any text has been pushed since the last finalize."""
        return bool(self._buffer)

    @property
    def buffer(self) -> str:
        """The accumulated text so far (without finalizing)."""
        return self._buffer

    def push(self, text: str) -> None:
        """Append a token and refresh the live-rendered markdown view.

        Empty input is a no-op (it would not change the rendered
        output and starting a render on the first empty push wastes a
        repaint).
        """
        if not text:
            return
        self._buffer += text
        if self._chat_app is not None:
            self._chat_app.push_chunk(text)

    async def finalize_async(self) -> str:
        """Flush the streamed text into scrollback and reset.

        Routes through :meth:`ChatApp.finalize_stream` when the
        renderer is bound to a live Application — that's the path
        production code takes inside ``_stream_events``.

        Returns the accumulated text. Safe to call when no stream has
        started; returns ``""`` in that case.
        """
        text = self._buffer
        self._buffer = ""
        if self._chat_app is None or not text:
            return text
        # ``finalize_stream`` raises ``RuntimeError`` when no event
        # loop / running Application is available — tests sometimes
        # finalize after teardown, so swallow that case so the
        # renderer still returns a coherent value.
        with contextlib.suppress(RuntimeError):
            await self._chat_app.finalize_stream()
        return text

    def finalize(self) -> str:
        """Synchronous reset — returns accumulated text and clears state.

        Production code uses :meth:`finalize_async` so the stream
        window flushes its content into terminal scrollback. This
        sync variant exists for test contexts (where no Application
        is running) and shutdown paths where ``await``ing isn't an
        option — it returns the same text and clears the in-memory
        buffer, leaving the Application (if any) to redraw with an
        empty stream on its next natural invalidate.
        """
        text = self._buffer
        self._buffer = ""
        if self._chat_app is not None:
            with contextlib.suppress(Exception):  # pragma: no cover — best effort
                self._chat_app.app.invalidate()
        return text
