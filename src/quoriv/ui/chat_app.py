"""Persistent prompt_toolkit Application that hosts the chat UI.

Phase 5 Slice 2 (v1.2.0): the chat loop used to spin up a fresh
``Application`` per input turn and let Rich own the terminal between
turns. That worked but meant prompt_toolkit and Rich were taking turns
holding the cursor — fine for plain text, ugly for streamed markdown,
and made HITL approval prompts (a ``PromptSession`` running between
two Rich renders) feel disjointed.

This module replaces the per-turn pattern with a **single
:class:`prompt_toolkit.Application` that lives for the whole chat
session**. Its layout is:

* A **stream window** (``FormattedTextControl`` wrapping ANSI-rendered
  markdown) that the agent's ``astream_events`` updates in place —
  no more Rich ``Live``.
* A **bordered input frame** at the bottom (the same Frame look as
  Phase 5 Slice 1).
* An **optional bottom toolbar** for the persistent status line.
* A :class:`FloatContainer` overlay that can host modal dialogs —
  used to render the HITL approval prompt in
  :func:`quoriv.ui.prompts.prompt_approval`.

The chat loop coroutine drives the Application by:

1. ``await app.prompt_input()`` — sets up an internal future that the
   ``Enter`` keybinding resolves with the buffer contents.
2. ``app.push_chunk(text)`` / ``await app.finalize_stream()`` — push
   tokens into the stream window during a turn, then commit the
   finished response to terminal scrollback so the window can clear
   itself for the next turn.
3. ``await app.prompt_approval(...)`` — install a modal Float and
   await the user's decision; the keybindings ``a`` / ``r`` / ``A``
   resolve the future.

All non-streaming output (welcome banner, slash command help, tool
diffs, errors) flows through ``app.console`` — a :class:`rich.Console`
whose ``file`` is a small adapter that forwards every Rich ``print``
into :meth:`Application.print_text` (which scrolls above the
Application area without interfering with the live render).

Design notes:

* ``run_in_terminal`` is used for printing-while-running. Calling
  ``Application.print_text`` directly while the renderer is live
  would corrupt the screen — the docstring on ``print_text`` says
  exactly this.
* The stream window uses ``dont_extend_height=True`` + a dynamic
  ``height`` so the inline Application grows with the response. On
  finalize we flush the rendered markdown into scrollback and clear
  the buffer in one atomic ``run_in_terminal`` callback — no flicker,
  no duplicate text.
* The approval modal is a :class:`prompt_toolkit.widgets.Dialog`
  wrapped in a :class:`Float`. While it's installed the modal owns
  focus and its own keybindings; the input buffer's bindings only
  fire for input-prompts, never approval-prompts.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import sys
from io import StringIO
from typing import TYPE_CHECKING, Any

from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import ANSI, to_formatted_text
from prompt_toolkit.history import History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Float, FloatContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.widgets import Dialog, Frame, Label
from rich.console import Console
from rich.markdown import Markdown

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from prompt_toolkit.completion import Completer

    from quoriv.ui.prompts import ApprovalDecision


# ---------------------------------------------------------------------------
# Rich → prompt_toolkit bridge
# ---------------------------------------------------------------------------


class _AppConsoleFile:
    """File-like object that forwards Rich output into the Application.

    Rich writes ANSI-coloured bytes to its ``file``. We collect them
    until ``flush()`` (or an explicit newline-bounded chunk) and then
    schedule a ``run_in_terminal`` call that emits the text above the
    Application's reserved area. The end result is that any caller
    using ``app.console.print(...)`` sees their content in terminal
    scrollback exactly as if Rich were the only thing writing.
    """

    __slots__ = ("_app", "_buf", "_loop")

    def __init__(self, app: ChatApp) -> None:
        self._app = app
        self._buf = ""
        # The chat loop's running asyncio loop. We don't capture it
        # eagerly because the ChatApp can be constructed before the
        # loop is running (e.g. in tests that just build the layout).
        self._loop: asyncio.AbstractEventLoop | None = None

    def write(self, s: str) -> int:
        if not isinstance(s, str):  # pragma: no cover — Rich always writes str
            s = str(s)
        self._buf += s
        return len(s)

    def flush(self) -> None:
        if not self._buf:
            return
        text = self._buf
        self._buf = ""
        self._app._schedule_scrollback_print(text)

    def isatty(self) -> bool:
        # Rich looks at this to decide whether to emit colour codes.
        # We're targeting a real terminal (prompt_toolkit's output),
        # so claim TTY.
        return True

    @property
    def encoding(self) -> str:
        return "utf-8"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


async def _await_in_terminal(func: Any) -> None:
    """Thin coroutine wrapper around :func:`run_in_terminal`.

    ``run_in_terminal`` is annotated as returning ``Awaitable[_T]`` —
    mypy refuses to attach ``add_done_callback`` to that. Wrapping it
    in an ``async`` function lets ``asyncio.ensure_future`` produce a
    proper ``Task`` we can introspect, at the cost of one extra await.
    """
    await run_in_terminal(func)


# ---------------------------------------------------------------------------
# Markdown rendering helper
# ---------------------------------------------------------------------------


def _render_markdown_to_ansi(text: str, *, width: int = 100) -> str:
    """Render a markdown string to ANSI-coloured terminal output.

    Used for both the streaming preview Window and the final scrollback
    flush. A fresh Console is built per call rather than reused so the
    ``record`` / ``file`` state can't leak between renderings.
    """
    if not text:
        return ""
    buf = StringIO()
    console = Console(
        file=buf,
        force_terminal=True,
        color_system="truecolor",
        width=width,
        soft_wrap=True,
    )
    console.print(Markdown(text))
    return buf.getvalue()


def _format_thinking_summary(thinking: str) -> str:
    """Collapse a reasoning trace to a single dim italic line.

    Returns the ANSI sequence ready to print above the answer in
    scrollback. Empty input returns ``""`` so callers can short-
    circuit. We don't echo the full chain-of-thought — most of it is
    private/model-specific scratchwork; the user's expectation is
    "I can see it streaming, but it shouldn't dominate scrollback".
    """
    if not thinking.strip():
        return ""
    n = len(thinking)
    # ANSI: italic + grey + "thought for N chars" + newline + reset.
    return f"\x1b[3;2;90m▸ Thought for {n:,} chars\x1b[0m\n"


# ---------------------------------------------------------------------------
# ChatApp — the persistent Application wrapper
# ---------------------------------------------------------------------------


_STATUS_VERBS: tuple[str, ...] = (
    "Brewing",
    "Cogitating",
    "Concocting",
    "Conjuring",
    "Contemplating",
    "Crafting",
    "Crystallizing",
    "Deliberating",
    "Devising",
    "Distilling",
    "Excogitating",
    "Forging",
    "Gestating",
    "Hatching",
    "Incubating",
    "Marinating",
    "Meditating",
    "Mulling",
    "Musing",
    "Noodling",
    "Percolating",
    "Pondering",
    "Reflecting",
    "Ruminating",
    "Scheming",
    "Simmering",
    "Sketching",
    "Synthesizing",
    "Tinkering",
    "Unspooling",
    "Weaving",
    "Wrangling",
)
"""Whimsical-but-readable verbs cycled through ``_status_text`` while a
non-reasoning model is generating but hasn't begun streaming yet.

The vocabulary is intentionally varied (and a little fancy — *Excogitating*,
*Crystallizing*, *Unspooling*) so the status indicator feels lively without
being annoying. Inspired by Claude Code's rotating "thinking" indicators.
"""


class ChatApp:
    """Persistent chat Application owning the prompt_toolkit layout.

    Construction is cheap and doesn't touch the terminal — instances
    can be built in tests for layout introspection. :meth:`run`
    actually starts the event loop.
    """

    def __init__(
        self,
        *,
        completer: Completer | None = None,
        history: History | None = None,
        bottom_toolbar: Callable[[], str] | None = None,
        frame_title: str = "quoriv",
        stream_width: int = 100,
        output: Any = None,
        input: Any = None,
    ) -> None:
        # Stream state. ``_stream_buffer`` is the in-flight markdown
        # being accumulated by ``push_chunk``; ``_get_stream_fragments``
        # re-renders it on every redraw so the visible markdown stays
        # current. ``_thinking_buffer`` (Slice 7) holds extended-
        # thinking / reasoning tokens — rendered in a dim italic block
        # above the answer so the user can see the model "think" but
        # the visual hierarchy keeps the answer primary.
        self._stream_buffer = ""
        self._thinking_buffer = ""
        self._stream_width = stream_width

        # Slice 8: rotating status verb for non-reasoning models that
        # don't emit a thinking stream. ``_status_text`` is the
        # currently-displayed verb; ``_status_task`` is the background
        # asyncio task that cycles it every ~3s. Both are ``None``
        # when no status is active.
        self._status_text: str | None = None
        self._status_task: asyncio.Task[None] | None = None

        # Pending interaction futures. At most one of these is non-None
        # at any moment; both default to None so a stray Enter while
        # nothing's awaiting is a no-op.
        self._input_future: asyncio.Future[str] | None = None
        self._approval_future: asyncio.Future[ApprovalDecision] | None = None
        self._exit_requested = False

        # Input buffer + frame.
        # Slice 9 (v1.6.1):
        #   * ``multiline=True`` so pasting text that contains
        #     newlines actually breaks into multiple lines instead of
        #     getting flattened. Our Enter keybinding still wins over
        #     prompt_toolkit's default "newline on Enter" behaviour,
        #     so Enter submits and Esc-Enter inserts a line break.
        #   * ``complete_while_typing`` is gated by a ``Condition``:
        #     the completer only fires when the buffer is short and
        #     starts with ``/`` (slash command discovery), which is
        #     the only path that actually needs the popup. Bulk
        #     pastes no longer fire 1000+ completer calls — paste
        #     becomes instant again.
        from prompt_toolkit.filters import Condition  # noqa: PLC0415
        from prompt_toolkit.layout.processors import (  # noqa: PLC0415
            ConditionalProcessor,
            PasswordProcessor,
        )

        self._input_buffer = Buffer(
            completer=completer,
            history=history if history is not None else InMemoryHistory(),
            multiline=True,
            complete_while_typing=Condition(
                lambda: (
                    self._input_buffer.text.startswith("/") and len(self._input_buffer.text) < 80
                )
            ),
        )

        self._password_mode: list[bool] = [False]
        self._input_control = BufferControl(
            buffer=self._input_buffer,
            input_processors=[
                ConditionalProcessor(
                    PasswordProcessor(),
                    Condition(lambda: self._password_mode[0]),
                ),
            ],
        )
        # Slice 9: input window grows with content. ``height=Dimension(min=1)``
        # means "at least one line, expand as needed"; ``wrap_lines=True``
        # lets long lines fold instead of disappearing off the right edge;
        # ``dont_extend_height=True`` caps growth at what's actually
        # needed so the input frame doesn't gobble vertical space when
        # the buffer is short.
        self._input_inner = Window(
            self._input_control,
            height=Dimension(min=1),
            wrap_lines=True,
            dont_extend_height=True,
        )
        self._input_frame = Frame(self._input_inner, title=frame_title)

        # Stream window — dynamic height that grows with content. The
        # ``height=Dimension(min=0)`` lets the window collapse to zero
        # lines when no stream is active so the input frame sits
        # directly under whatever Rich just printed.
        self._stream_control = FormattedTextControl(
            text=self._get_stream_fragments,
            focusable=False,
            show_cursor=False,
        )
        self._stream_window = Window(
            self._stream_control,
            wrap_lines=True,
            dont_extend_height=True,
            height=Dimension(min=0),
        )

        # Slice 5: inline picker — renders an arrow-key-driven numbered
        # list directly in the chat area (above the input frame). Unlike
        # ``select_option_modal`` it isn't a Float — it's a normal Window
        # in the HSplit, gated by ``_picker_active`` via a
        # ``ConditionalContainer``, so it occupies real layout space and
        # never overflows like a Float can. This is the Claude-Code-style
        # ``/model`` chooser the user asked for.
        from prompt_toolkit.layout.containers import (  # noqa: PLC0415
            ConditionalContainer,
        )

        self._picker_active: list[bool] = [False]
        self._picker_state: dict[str, Any] = {
            "options": [],
            "index": 0,
            "title": "",
            "description": "",
            "future": None,
        }
        self._picker_control = FormattedTextControl(
            text=self._get_picker_fragments,
            focusable=True,
            show_cursor=False,
            key_bindings=self._build_picker_key_bindings(),
        )
        self._picker_window = Window(
            self._picker_control,
            wrap_lines=True,
            dont_extend_height=True,
        )
        self._picker_container = ConditionalContainer(
            content=self._picker_window,
            filter=Condition(lambda: self._picker_active[0]),
        )

        # Slice 8: rotating "Pondering…" / "Concocting…" status row.
        # Renders as a single italic-grey line above the input frame,
        # only visible when ``_status_text`` is set. Used to keep the
        # user engaged while a non-reasoning model is generating but
        # hasn't started streaming text yet (or in the gap between a
        # tool returning and the model resuming).
        self._status_control = FormattedTextControl(
            text=self._get_status_fragments,
            focusable=False,
            show_cursor=False,
        )
        self._status_window = Window(
            self._status_control,
            height=1,
            dont_extend_height=True,
        )
        self._status_container = ConditionalContainer(
            content=self._status_window,
            filter=Condition(lambda: self._status_text is not None),
        )

        # Bottom toolbar (optional, mirrors the Slice 1 status line).
        children: list[Any] = [
            self._stream_window,
            self._status_container,
            self._picker_container,
            self._input_frame,
        ]
        if bottom_toolbar is not None:
            children.append(
                Window(
                    FormattedTextControl(bottom_toolbar),
                    height=1,
                    style="class:bottom-toolbar",
                )
            )

        # FloatContainer wraps the HSplit so modal dialogs can overlay
        # both the stream and the input box. Modals are installed by
        # appending to ``self._float_container.floats`` and removed in
        # the awaiting coroutine's ``finally``.
        #
        # The persistent ``CompletionsMenu`` Float is the inline
        # autocomplete popup that fires while the user types: without
        # it, ``complete_while_typing=True`` on the input buffer has
        # nowhere to render its suggestions. ``xcursor=True`` /
        # ``ycursor=True`` anchor the menu at the buffer's cursor; in
        # inline mode prompt_toolkit positions it above the cursor
        # when there isn't enough room below, which is exactly what
        # we want — the menu pops upward into terminal scrollback so
        # the chat content stays visible.
        self._float_container = FloatContainer(
            content=HSplit(children),
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=10, scroll_offset=1),
                ),
            ],
        )

        self._key_bindings = self._build_key_bindings()

        app_kwargs: dict[str, Any] = {
            "layout": Layout(
                self._float_container,
                focused_element=self._input_inner,
            ),
            "key_bindings": self._key_bindings,
            "full_screen": False,
            "mouse_support": False,
        }
        if output is not None:
            app_kwargs["output"] = output
        if input is not None:
            app_kwargs["input"] = input
        self.app: Application[Any] = Application(**app_kwargs)

        # Rich console whose output is routed into the Application's
        # scrollback. Constructed lazily so tests that just want layout
        # introspection don't pay for it.
        self._console_file = _AppConsoleFile(self)
        self._console: Console | None = None

    # ----- Public state ---------------------------------------------------

    @property
    def console(self) -> Console:
        """Rich :class:`Console` that writes into the Application's scrollback.

        Use this instead of constructing your own console — anything
        printed through it lands above the persistent layout via
        ``app.print_text`` (which is safe even mid-render thanks to the
        ``run_in_terminal`` scheduling in :class:`_AppConsoleFile`).
        """
        if self._console is None:
            # Rich's ``Console`` typing wants ``IO[str]``; our adapter
            # implements the subset Rich actually uses (write / flush /
            # isatty / encoding) but isn't a full ``IO[str]`` instance.
            # Cast is safe and keeps mypy quiet.
            from typing import IO, cast  # noqa: PLC0415  (narrow scope)

            self._console = Console(
                file=cast("IO[str]", self._console_file),
                force_terminal=True,
                color_system="truecolor",
                width=self._stream_width,
            )
        return self._console

    @property
    def stream_buffer(self) -> str:
        """Current in-flight streamed markdown text (testing hook)."""
        return self._stream_buffer

    @property
    def is_streaming(self) -> bool:
        """True if any text or thinking has been pushed since finalize."""
        return bool(self._stream_buffer or self._thinking_buffer)

    @property
    def thinking_buffer(self) -> str:
        """Current in-flight reasoning / thinking text (testing hook)."""
        return self._thinking_buffer

    # ----- Lifecycle ------------------------------------------------------

    async def run(self, driver: Callable[[], Awaitable[None]]) -> None:
        """Start the persistent Application and the chat-driver coroutine.

        The Application runs until either:

        * the driver coroutine returns (clean exit — the chat loop
          handles ``/exit``, ``EOFError``, etc.), or
        * an exception bubbles out of the driver (re-raised here after
          the Application is torn down).

        The driver coroutine is started as a background task **after**
        the Application begins running so its first ``await
        prompt_input()`` finds the Application already pumping events.
        """
        driver_task: asyncio.Task[None] | None = None
        driver_exc: BaseException | None = None

        def _record(task: asyncio.Task[None]) -> None:
            nonlocal driver_exc
            if task.cancelled():
                return
            exc = task.exception()
            if exc is not None:
                driver_exc = exc
            # Whether the driver finished cleanly or raised, the
            # Application should exit so ``run_async`` returns.
            if not self.app.is_done:
                self.app.exit()

        def _pre_run() -> None:
            # ``pre_run`` fires synchronously inside the running event
            # loop, just before the Application starts pumping events.
            # Spawning the driver coroutine here guarantees its first
            # ``await prompt_input()`` finds the Application alive.
            nonlocal driver_task
            driver_task = asyncio.create_task(driver())  # type: ignore[arg-type]
            driver_task.add_done_callback(_record)

        try:
            await self.app.run_async(pre_run=_pre_run)
        finally:
            if driver_task is not None and not driver_task.done():
                driver_task.cancel()
                with contextlib.suppress(BaseException):
                    await driver_task
        if driver_exc is not None:
            raise driver_exc

    def exit(self) -> None:
        """Request the Application to exit at the next safe point.

        Used by ``/exit`` / ``/quit`` after they finish writing their
        goodbye line.
        """
        self._exit_requested = True
        if not self.app.is_done:
            self.app.exit()

    # ----- Input prompt ---------------------------------------------------

    async def prompt_input(
        self,
        *,
        completer: Any = None,
        password: bool = False,
        open_completion: bool = False,
    ) -> str:
        """Wait for the user to submit a line of input.

        Args:
            completer: Optional one-shot completer. Overrides the
                buffer's default completer for the duration of this
                prompt; restored on return so the chat loop's slash
                completer is unaffected. Useful for picker prompts
                during the ``/login`` flow.
            password: When ``True`` the buffer renders typed
                characters as ``*`` (still committed verbatim). Used
                for API-key entry.
            open_completion: When ``True``, programmatically open the
                completion menu as soon as the prompt becomes active
                so the dropdown is visible without the user typing a
                character first. Pair with ``completer=`` for "pick
                from list" prompts.

        Raises:
            EOFError: When the user pressed Ctrl+C or Ctrl+D — mirrors
                ``PromptSession.prompt_async`` so the chat loop's
                existing exception handling keeps working.
        """
        if self._input_future is not None:
            raise RuntimeError("prompt_input() is already awaiting")

        original_completer = self._input_buffer.completer
        if completer is not None:
            self._input_buffer.completer = completer
        original_password = self._password_mode[0]
        self._password_mode[0] = password

        loop = asyncio.get_running_loop()
        self._input_future = loop.create_future()

        if open_completion and not self.app.is_done:
            # Kick the completion menu open one event-loop tick after
            # the prompt becomes active so the dropdown is visible
            # without the user typing first. ``start_completion`` is
            # safe to call when no completer is bound — it's a no-op
            # in that case.
            def _kick() -> None:
                with contextlib.suppress(Exception):
                    self._input_buffer.start_completion(select_first=True)
                    self.app.invalidate()

            loop.call_soon(_kick)

        try:
            return await self._input_future
        finally:
            self._input_future = None
            self._input_buffer.completer = original_completer
            self._password_mode[0] = original_password

    # ----- Stream window --------------------------------------------------

    def push_chunk(self, text: str) -> None:
        """Append a streamed token to the in-flight markdown buffer.

        Empty input is a no-op — matches the legacy
        :class:`quoriv.ui.stream.StreamRenderer` semantics so callers
        can blindly forward LangChain chunks.
        """
        if not text:
            return
        # Real content is arriving — kill the rotating status verb
        # so it doesn't sit next to the actual answer.
        self.stop_status()
        self._stream_buffer += text
        if not self.app.is_done:
            self.app.invalidate()

    def push_thinking(self, text: str) -> None:
        """Append reasoning / thinking tokens to the in-flight buffer.

        Rendered in a dim italic block above the answer in the stream
        window. The text accumulates separately from the answer so
        :meth:`finalize_stream` can collapse it on flush (we keep
        "thought for N chars" in scrollback, not the full chain-of-
        thought — saves vertical space and matches Claude Code).
        Empty input is a no-op.
        """
        if not text:
            return
        # Any real reasoning supersedes the rotating status verb —
        # the user can see the model is actually generating now.
        self.stop_status()
        self._thinking_buffer += text
        if not self.app.is_done:
            self.app.invalidate()

    # ----- Status verb rotation -------------------------------------------

    def set_status(self, text: str | None) -> None:
        """Set the inline status line (e.g. ``Pondering…``).

        Pass ``None`` to hide. The status row is only visible while
        ``_status_text`` is non-None — the ``ConditionalContainer``
        in the layout takes care of collapsing the row otherwise.
        """
        self._status_text = text
        if not self.app.is_done:
            self.app.invalidate()

    def start_status(self, *, interval: float = 3.0) -> None:
        """Begin cycling a random verb every ``interval`` seconds.

        Used between "user submitted" and "first chunk arrived" so a
        non-reasoning model doesn't appear frozen. Calling this while
        a rotation is already running is a no-op.

        Skipped silently when there's no running event loop or no
        Application yet (test contexts).
        """
        if self._status_task is not None and not self._status_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _rotate() -> None:
            verbs = list(_STATUS_VERBS)
            random.shuffle(verbs)
            idx = 0
            try:
                while True:
                    self.set_status(f"{verbs[idx]}…")
                    idx = (idx + 1) % len(verbs)
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                # Normal stop path — propagate so the task ends.
                raise

        self._status_task = loop.create_task(_rotate())

    def stop_status(self) -> None:
        """Cancel the rotation and clear the status line.

        Safe to call repeatedly. Used when the first chunk arrives,
        when a tool call starts (the tool label takes over), and at
        turn teardown.
        """
        if self._status_task is not None:
            if not self._status_task.done():
                self._status_task.cancel()
            self._status_task = None
        if self._status_text is not None:
            self.set_status(None)

    def _get_status_fragments(self) -> list[tuple[str, str]]:
        """Render the status row — one italic-grey line, or empty."""
        if not self._status_text:
            return []
        return [("italic ansigray", f"  ▸ {self._status_text}\n")]

    async def finalize_stream(self) -> str:
        """Flush the current stream to scrollback and clear the window.

        Renders the accumulated markdown to ANSI once, prints it above
        the Application area (so it lands in terminal scrollback the
        same way Rich's pre-Slice-2 output did), then clears the
        in-window buffer. The print and the clear happen inside a
        single ``run_in_terminal`` callback so the screen never shows
        an intermediate "empty stream + nothing in scrollback" state.

        When a thinking buffer is present it's collapsed to a single
        ``▸ Thought for N chars`` line that flushes alongside the
        answer — the full chain-of-thought is not echoed to
        scrollback (it stays visible only during streaming).

        Safe to call when no stream is active — returns ``""``.
        """
        if not self._stream_buffer and not self._thinking_buffer:
            return ""
        text = self._stream_buffer
        thinking = self._thinking_buffer
        rendered = _render_markdown_to_ansi(text, width=self._stream_width)
        thinking_summary = _format_thinking_summary(thinking)

        def _flush() -> None:
            self._stream_buffer = ""
            self._thinking_buffer = ""
            if thinking_summary:
                # Print the collapsed "thought for N chars" line first
                # so it sits above the answer in scrollback.
                self.app.print_text(ANSI(thinking_summary))
            if rendered:
                self.app.print_text(ANSI(rendered))

        if self.app.is_done:
            # Tests / shutdown path — just write directly.
            self._stream_buffer = ""
            self._thinking_buffer = ""
        else:
            await run_in_terminal(_flush)
        return text

    def _get_stream_fragments(self) -> Any:
        """Build the FormattedText fragments shown in the stream window."""
        if not self._stream_buffer and not self._thinking_buffer:
            return to_formatted_text("")
        out: list[tuple[str, str]] = []
        if self._thinking_buffer:
            # Header
            out.append(("italic ansicyan", "▸ Thinking…\n"))
            # Body — dim italic so the answer below remains primary.
            for line in self._thinking_buffer.splitlines() or [self._thinking_buffer]:
                out.append(("italic ansigray", f"  {line}\n"))
            if self._stream_buffer:
                out.append(("", "\n"))
        if self._stream_buffer:
            rendered = _render_markdown_to_ansi(self._stream_buffer, width=self._stream_width)
            return out + list(ANSI(rendered).__pt_formatted_text__())
        return out

    # ----- Inline picker (Claude-Code-style numbered list) ----------------

    def _get_picker_fragments(self) -> list[tuple[str, str]]:
        """Render the inline picker as Claude-Code-style numbered list.

        Layout:
            <blank line>
            ─ separator ─
            Title (bold cyan)
            Description (white, optional)
            <blank line>
              1. Label   ← highlighted with "> " prefix when current
              2. Label
              ...
            <blank line>
            (hint: ↑/↓ navigate · Enter select · Esc cancel)
        """
        state = self._picker_state
        options: list[tuple[str, str]] = state.get("options", [])
        index: int = state.get("index", 0)
        title: str = state.get("title", "")
        description: str = state.get("description", "")

        fragments: list[tuple[str, str]] = [("", "\n")]
        # Subtle separator above the picker section.
        fragments.append(("class:picker.separator", "─" * 70 + "\n"))
        if title:
            fragments.append(("bold ansicyan", f"  {title}\n"))
        if description:
            fragments.append(("ansigray", f"  {description}\n"))
        fragments.append(("", "\n"))

        for i, opt in enumerate(options):
            value, label = opt[0], opt[1]
            number = f"{i + 1}."
            if i == index:
                fragments.append(("ansiyellow bold", f"  > {number} "))
                fragments.append(("ansiwhite bold", f"{value}"))
                if label and label != value:
                    fragments.append(("ansigray", f"   {label}"))
                fragments.append(("", "\n"))
            else:
                fragments.append(("ansigray", f"    {number} "))
                fragments.append(("ansiwhite", f"{value}"))
                if label and label != value:
                    fragments.append(("ansigray", f"   {label}"))
                fragments.append(("", "\n"))

        fragments.append(("", "\n"))
        fragments.append(
            (
                "ansigray italic",
                "  up/down navigate   Enter select   Esc cancel\n",
            )
        )
        fragments.append(("", "\n"))
        return fragments

    def _build_picker_key_bindings(self) -> KeyBindings:
        """Key bindings active when the inline picker has focus.

        These only fire when ``self._picker_window`` is the focused
        control, so they don't conflict with the input buffer's
        global bindings.
        """
        kb = KeyBindings()

        def _resolve(value: str | None) -> None:
            future = self._picker_state.get("future")
            if future is not None and not future.done():
                future.set_result(value)

        @kb.add("up")
        @kb.add("c-p")
        def _up(event: Any) -> None:
            if self._picker_state["index"] > 0:
                self._picker_state["index"] -= 1
                event.app.invalidate()

        @kb.add("down")
        @kb.add("c-n")
        def _down(event: Any) -> None:
            options = self._picker_state.get("options", [])
            if self._picker_state["index"] < len(options) - 1:
                self._picker_state["index"] += 1
                event.app.invalidate()

        @kb.add("home")
        @kb.add("pageup")
        def _top(event: Any) -> None:
            self._picker_state["index"] = 0
            event.app.invalidate()

        @kb.add("end")
        @kb.add("pagedown")
        def _bottom(event: Any) -> None:
            options = self._picker_state.get("options", [])
            if options:
                self._picker_state["index"] = len(options) - 1
            event.app.invalidate()

        @kb.add("enter")
        def _select(event: Any) -> None:
            options = self._picker_state.get("options", [])
            if not options:
                _resolve(None)
                return
            value = options[self._picker_state["index"]][0]
            _resolve(value)

        @kb.add("escape")
        @kb.add("c-c")
        def _cancel(event: Any) -> None:
            _resolve(None)

        # Number shortcuts (1-9) jump-and-confirm.
        for i in range(1, 10):

            @kb.add(str(i))
            def _by_number(event: Any, n: int = i) -> None:
                options = self._picker_state.get("options", [])
                if 1 <= n <= len(options):
                    self._picker_state["index"] = n - 1
                    _resolve(options[n - 1][0])

        return kb

    async def prompt_picker(
        self,
        *,
        title: str,
        description: str = "",
        options: list[tuple[str, str]],
    ) -> str | None:
        """Show an inline picker section and return the chosen value.

        Renders as a Claude-Code-style numbered list directly inside
        the chat area (above the input frame, below the stream
        window). Unlike :meth:`select_option_modal` / the v1.3.x
        Float-based picker, this consumes real layout space — there
        is no floating box, no risk of "Window too small" overflow,
        and no separate visual canvas. Up/down move the highlight;
        digit keys ``1`` through ``9`` jump-and-confirm; ``Enter``
        selects the highlighted row; ``Esc`` / ``Ctrl+C`` cancel.

        Args:
            title: Header text shown above the list (e.g. "Select
                model").
            description: Optional one-line subtitle under the
                header. Pass empty string to suppress.
            options: Ordered ``(value, label)`` pairs. ``value`` is
                what gets returned; ``label`` is the human-readable
                description shown next to it.

        Returns:
            The chosen value, or ``None`` if the user cancelled.
            Returns ``None`` immediately when ``options`` is empty.
        """
        if not options:
            return None

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str | None] = loop.create_future()

        self._picker_state.update(
            {
                "options": list(options),
                "index": 0,
                "title": title,
                "description": description,
                "future": future,
            }
        )
        self._picker_active[0] = True

        prev_focus = self.app.layout.current_window
        with contextlib.suppress(Exception):  # pragma: no cover — headless fallback
            self.app.layout.focus(self._picker_window)
        if not self.app.is_done:
            self.app.invalidate()

        try:
            return await future
        finally:
            self._picker_active[0] = False
            self._picker_state["future"] = None
            if prev_focus is not None:
                with contextlib.suppress(Exception):
                    self.app.layout.focus(prev_focus)
            if not self.app.is_done:
                self.app.invalidate()

    # ----- Console scrollback ---------------------------------------------

    def _schedule_scrollback_print(self, text: str) -> None:
        """Forward a Rich-formatted block to the Application's scrollback.

        Always-safe entry point: works whether the Application is
        running, not yet started, or already exited. The branching:

        * App running → schedule a ``run_in_terminal`` task that prints
          the text above the live render.
        * App not yet started (tests / pre-run banner) → buffer the
          text into the stream buffer so the very next render shows
          it. We can't legally call ``print_text`` here.
        * App already done → write directly to the underlying output.
        """
        if not text:
            return
        if self.app.is_done:
            # Final teardown — bypass the Application entirely.
            try:
                self.app.output.write_raw(text)
                self.app.output.flush()
            except Exception:  # pragma: no cover — best-effort fallback
                # Last resort: write to real stderr so the message
                # isn't silently lost.
                sys.stderr.write(text)
            return
        if not self.app.is_running:
            # Pre-run output (welcome banner). Stash on the stream
            # buffer so the first render shows it. The chat-driver
            # coroutine clears this after the user's first input.
            self._stream_buffer += text
            return

        # Hot path: schedule an in-terminal print. We can't ``await``
        # here (this is sync from Rich's perspective), so fire-and-
        # forget. ``run_in_terminal`` is annotated ``Awaitable`` but is
        # implemented as ``ensure_future(run())`` — wrap the result in
        # ``ensure_future`` so mypy sees a Task we can attach a
        # done-callback to.
        fut = asyncio.ensure_future(_await_in_terminal(lambda: self.app.print_text(ANSI(text))))

        def _log_exc(f: asyncio.Future[Any]) -> None:
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:  # pragma: no cover — defensive
                sys.stderr.write(f"chat_app scrollback print failed: {exc!r}\n")

        fut.add_done_callback(_log_exc)

    def clear_transcript(self) -> None:
        """Erase any pending scrollback / stream state.

        Used by ``/clear``. The terminal's own scrollback isn't
        cleared (that's the terminal emulator's job); we just reset
        the in-flight stream + thinking buffers so the next render
        starts fresh.
        """
        self._stream_buffer = ""
        self._thinking_buffer = ""
        if not self.app.is_done:
            self.app.invalidate()

    # ----- Approval modal -------------------------------------------------

    async def prompt_approval_modal(
        self,
        *,
        body_text: str,
        title: str = "approval required",
    ) -> str:
        """Show a modal approval dialog and return the user's choice.

        The dialog body is pre-rendered ANSI text (typically a
        Rich-rendered panel) — keeping the rendering decision in the
        ``prompts`` module so this class doesn't need to know about
        tool args.

        Returns one of ``"approve"`` / ``"approve_always"`` /
        ``"reject"``. The :mod:`quoriv.ui.prompts` wrapper converts
        that into a full :class:`ApprovalDecision`.
        """
        if self._approval_future is not None:
            raise RuntimeError("prompt_approval_modal() is already awaiting")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._approval_future = future  # type: ignore[assignment]

        modal_kb = KeyBindings()

        def _resolve(choice: str) -> None:
            if not future.done():
                future.set_result(choice)

        @modal_kb.add("a")
        @modal_kb.add("y")
        def _approve(event: Any) -> None:
            _resolve("approve")

        @modal_kb.add("A")
        def _approve_always(event: Any) -> None:
            _resolve("approve_always")

        @modal_kb.add("r")
        @modal_kb.add("n")
        def _reject(event: Any) -> None:
            _resolve("reject")

        @modal_kb.add("escape")
        @modal_kb.add("c-c")
        def _cancel(event: Any) -> None:
            _resolve("reject")

        # Dialog body: ANSI panel + a one-line hint. Wrapped in a
        # Window so prompt_toolkit can size it correctly.
        body_label = Label(ANSI(body_text), dont_extend_height=True)
        hint = Label(
            ANSI("\n  [a] approve   [r] reject   [A] approve always   [Esc] cancel\n"),
            dont_extend_height=True,
        )
        dialog = Dialog(
            body=HSplit([body_label, hint], key_bindings=modal_kb),
            title=title,
            with_background=True,
            modal=True,
        )

        modal_float = Float(content=dialog)
        self._float_container.floats.append(modal_float)
        # Stash the previous focus so we can restore it.
        prev_focus = self.app.layout.current_window
        with contextlib.suppress(Exception):  # pragma: no cover — headless fallback
            self.app.layout.focus(dialog)
        if not self.app.is_done:
            self.app.invalidate()

        try:
            return await future
        finally:
            self._approval_future = None
            with contextlib.suppress(ValueError):
                self._float_container.floats.remove(modal_float)
            if prev_focus is not None:
                with contextlib.suppress(Exception):
                    self.app.layout.focus(prev_focus)
            if not self.app.is_done:
                self.app.invalidate()

    # ----- Option picker --------------------------------------------------

    async def select_option_modal(  # noqa: PLR0915 — small inline picker scope
        self,
        *,
        title: str,
        options: Sequence[tuple[str, str]],
        current: str | None = None,
    ) -> str | None:
        """Show an arrow-key dropdown picker and return the chosen value.

        Args:
            title: Header shown at the top of the Dialog.
            options: List of ``(value, label)`` pairs. ``value`` is
                what gets returned; ``label`` is what the user sees.
            current: Optional value that should be pre-highlighted —
                useful for ``/mode`` where we want the active mode
                selected by default.

        Returns:
            The chosen ``value`` or ``None`` when the user cancels
            (Esc / Ctrl+C). Returns ``None`` immediately when
            ``options`` is empty (no choices → no picker).

        Bindings:
            * ``↑`` / ``↓`` move the highlight.
            * ``Home`` / ``End`` jump to the first / last item.
            * ``Enter`` confirms.
            * ``Esc`` or ``Ctrl+C`` cancel.

        While the picker is up the input buffer's bindings are
        suspended (the focus guard in :meth:`_build_key_bindings`
        skips them), so the up/down/enter keys go to the picker only.
        """
        if not options:
            return None

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str | None] = loop.create_future()

        # Pre-select ``current`` when supplied.
        initial_idx = 0
        if current is not None:
            for i, (value, _label) in enumerate(options):
                if value == current:
                    initial_idx = i
                    break
        state: dict[str, int] = {"index": initial_idx}

        def render() -> list[tuple[str, str]]:
            fragments: list[tuple[str, str]] = []
            for i, (_value, label) in enumerate(options):
                if i == state["index"]:
                    fragments.append(("reverse bold", f" > {label} \n"))
                else:
                    fragments.append(("", f"   {label} \n"))
            return fragments

        kb = KeyBindings()

        def _resolve(value: str | None) -> None:
            if not future.done():
                future.set_result(value)

        @kb.add("up")
        def _up(event: Any) -> None:
            if state["index"] > 0:
                state["index"] -= 1
                event.app.invalidate()

        @kb.add("down")
        def _down(event: Any) -> None:
            if state["index"] < len(options) - 1:
                state["index"] += 1
                event.app.invalidate()

        @kb.add("home")
        @kb.add("pageup")
        def _top(event: Any) -> None:
            state["index"] = 0
            event.app.invalidate()

        @kb.add("end")
        @kb.add("pagedown")
        def _bottom(event: Any) -> None:
            state["index"] = len(options) - 1
            event.app.invalidate()

        @kb.add("enter")
        def _select(event: Any) -> None:
            _resolve(options[state["index"]][0])

        @kb.add("escape")
        @kb.add("c-c")
        def _cancel(event: Any) -> None:
            _resolve(None)

        body_control = FormattedTextControl(
            text=render,
            focusable=True,
            show_cursor=False,
            key_bindings=kb,
        )
        body_window = Window(
            body_control,
            # ``wrap_lines=True`` lets long option labels fold onto
            # multiple lines instead of triggering prompt_toolkit's
            # "Window too small..." overflow message in narrow
            # terminals.
            wrap_lines=True,
            dont_extend_height=True,
            # Height is at least one line per option but allowed to
            # grow when wrapping kicks in.
            height=Dimension(min=len(options)),
        )
        hint = Window(
            FormattedTextControl(text=ANSI(" up/down navigate  enter select  esc cancel ")),
            height=1,
            style="class:completion-menu.meta",
        )
        # Slice 3 polish: render the picker as a Frame anchored just
        # above the input box rather than a centred Dialog with a dim
        # backdrop. The visual result is Claude-Code-style: chat stays
        # visible behind the popup, popup hugs the input frame, no
        # full-screen modal feel.
        picker_frame = Frame(HSplit([body_window, hint]), title=title)
        # ``bottom=4`` places the float's bottom edge 4 lines above the
        # screen bottom — that's input-frame-top + toolbar (3+1).
        # ``left=1`` mirrors the chat indent. ``right`` is intentionally
        # omitted so the Float can size itself to its content (or shrink
        # to whatever fits) instead of forcing a minimum width that
        # narrow terminals can't honour.
        modal_float = Float(content=picker_frame, bottom=4, left=1)
        self._float_container.floats.append(modal_float)
        prev_focus = self.app.layout.current_window
        with contextlib.suppress(Exception):  # pragma: no cover — headless fallback
            self.app.layout.focus(body_window)
        if not self.app.is_done:
            self.app.invalidate()

        try:
            return await future
        finally:
            with contextlib.suppress(ValueError):
                self._float_container.floats.remove(modal_float)
            if prev_focus is not None:
                with contextlib.suppress(Exception):
                    self.app.layout.focus(prev_focus)
            if not self.app.is_done:
                self.app.invalidate()

    # ----- Internals ------------------------------------------------------

    def _build_key_bindings(self) -> KeyBindings:
        """Build the input-buffer keybindings.

        Bindings only fire when the input buffer is focused — the
        approval modal installs its own keybindings on its inner
        container and owns focus while it's up, so ``Enter`` and
        ``a``/``r``/``A`` route to the modal not here.
        """
        kb = KeyBindings()

        def _input_focused(event: Any) -> bool:
            """True when the chat input buffer owns focus.

            Used to guard global bindings so they don't fire while a
            modal Float (approval, option picker) is up and has
            installed its own keybindings.
            """
            return event.app.layout.current_control is self._input_control

        @kb.add("enter")
        def _submit(event: Any) -> None:
            if not _input_focused(event):
                return
            buf = event.current_buffer

            # Claude-Code-style inline typeahead: if the autocomplete
            # menu is open and the user has highlighted a completion,
            # apply it before deciding whether to submit. Completions
            # whose text ends with a space (command names like
            # ``/mode ``) keep the cursor in the buffer so the user
            # can flow into argument completion; completions without
            # a trailing space (concrete arguments like ``auto``)
            # apply *and* submit in a single Enter press.
            if buf.complete_state is not None:
                completion = buf.complete_state.current_completion
                if completion is not None:
                    buf.apply_completion(completion)
                    if completion.text.endswith(" "):
                        buf.complete_state = None
                        return

            fut = self._input_future
            if fut is None or fut.done():
                return
            text = self._input_buffer.text
            self._input_buffer.reset()
            fut.set_result(text)

        @kb.add("c-c")
        @kb.add("c-d")
        def _abort(event: Any) -> None:
            if not _input_focused(event):
                # A modal is focused — let its own bindings handle it.
                return
            fut = self._input_future
            if fut is not None and not fut.done():
                fut.set_exception(EOFError())
                return
            # No input prompt active — exit the app entirely.
            self._exit_requested = True
            event.app.exit()

        @kb.add("escape", "enter")
        def _newline(event: Any) -> None:
            if not _input_focused(event):
                return
            self._input_buffer.insert_text("\n")

        return kb
