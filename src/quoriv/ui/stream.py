"""Streaming markdown renderer for LLM output.

Wraps Rich ``Live`` + ``Markdown`` so token-by-token output renders with
markdown semantics (bold, lists, code blocks, inline code) instead of
plain text.

Usage:
    renderer = StreamRenderer(console)
    renderer.push("Hello, ")
    renderer.push("**world**")
    text = renderer.finalize()  # closes the Live; returns full text

Phase 1 Slice 3 keeps this simple. Partial markdown (e.g. an open
code fence mid-stream) re-renders on every chunk; Rich's incremental
output keeps flicker manageable for typical chat responses.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from rich.live import Live
from rich.markdown import Markdown

if TYPE_CHECKING:
    from rich.console import Console


class StreamRenderer:
    """Accumulate streamed tokens and live-render them as markdown."""

    __slots__ = ("_buffer", "_console", "_live")

    def __init__(self, console: Console) -> None:
        self._console = console
        self._live: Live | None = None
        self._buffer = ""

    @property
    def is_streaming(self) -> bool:
        """True if a Live render is currently active."""
        return self._live is not None

    @property
    def buffer(self) -> str:
        """The accumulated text so far (without finalizing)."""
        return self._buffer

    def push(self, text: str) -> None:
        """Append a token and refresh the live-rendered markdown view.

        Empty input is a no-op (it would not change the rendered output
        and starting a Live on the first empty push wastes a refresh).
        """
        if not text:
            return
        self._buffer += text
        if self._live is None:
            self._live = Live(
                Markdown(self._buffer),
                console=self._console,
                refresh_per_second=8,
                auto_refresh=True,
            )
            self._live.start()
        else:
            self._live.update(Markdown(self._buffer))

    def finalize(self) -> str:
        """Stop the Live render and return the accumulated text.

        Safe to call when no stream has started; returns ``""`` in that
        case. After calling, the renderer is reset and ready to start a
        new stream via :meth:`push`.
        """
        text = self._buffer
        if self._live is not None:
            with contextlib.suppress(Exception):
                # Rich can raise on already-stopped Live; tolerate it.
                self._live.stop()
            self._live = None
        self._buffer = ""
        return text
