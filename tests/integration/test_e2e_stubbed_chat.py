"""End-to-end integration test for the chat turn pipeline.

Slice 9b: validates that a real :func:`quoriv.core.build_agent`
invocation, driven through :func:`quoriv.app._drive_turn`, streams
events through the :class:`StreamRenderer`, writes the expected
``turn_start`` / ``model_complete`` / ``turn_end`` records to the
per-thread JSONL trace log, and produces a well-formed status line —
all without ever calling a real LLM provider.

The stub model is a thin subclass of :class:`GenericFakeChatModel` with
``bind_tools`` short-circuited to ``self`` (the base class raises
``NotImplementedError``). DeepAgents binds tools onto the model when
compiling the agent, so the override is required for the agent to
build. Since the stub never emits ``tool_calls``, the agent finishes in
one model turn — exactly the happy path Slice 9b cares about.

What this test buys us beyond the per-module unit tests:
    * Confirms the LangGraph event stream ordering Quoriv assumes
      (``on_chat_model_stream`` → ``on_chat_model_end``) survives the
      DeepAgents wrapping + checkpointer wiring + middleware chain.
    * Catches accidental regressions where ``_drive_turn`` /
      ``_stream_events`` / ``TraceLogger`` drift out of sync — e.g. a
      renamed event key, a missing tracer call, a status-line format
      change.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console

from quoriv.app import _build_status_line, _drive_turn
from quoriv.config.schema import QuorivConfig
from quoriv.core import build_agent, trace_path
from quoriv.observability import TraceLogger


class _StubChatModel(GenericFakeChatModel):
    """``GenericFakeChatModel`` whose ``bind_tools`` returns ``self``.

    DeepAgents' tool wiring relies on ``model.bind_tools(tools)``; the
    fake model in ``langchain_core`` raises ``NotImplementedError`` for
    it. Overriding to return ``self`` lets the agent compile without a
    real provider.
    """

    def bind_tools(self, _tools: Any, **_kwargs: Any) -> Any:  # type: ignore[override]
        return self


def _stub_console() -> tuple[Console, StringIO]:
    """Build a Rich console writing to an in-memory buffer.

    ``force_terminal=False`` keeps ``rich.live.Live`` in a no-op mode
    that doesn't try to repaint the terminal — required for the
    :class:`StreamRenderer` inside ``_stream_events`` to coexist with
    ``StringIO``.
    """
    buf = StringIO()
    return Console(file=buf, width=10_000, force_terminal=False, no_color=True), buf


def _read_trace(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL trace file into a list of dict records."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _make_stub_agent(
    monkeypatch: Any,
    tmp_path: Path,
    *,
    response: str = "hello from the stub",
    repeats: int = 8,
) -> Any:
    """Build a real Quoriv agent, replacing the LLM with a stub.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        tmp_path: cwd root for the agent's filesystem/shell.
        response: Body of the ``AIMessage`` the stub emits per turn.
        repeats: How many pre-loaded responses to queue. DeepAgents
            sometimes invokes the model more than once per turn during
            tool routing — over-supplying avoids ``StopIteration`` on
            ``next(messages)``.
    """
    msgs = iter([AIMessage(content=response) for _ in range(repeats)])
    stub = _StubChatModel(messages=msgs)
    # Phase 2 Slice 4 added subagents — each one resolves its own
    # model through ``quoriv.core.subagents.get_model``. Patch both
    # references so the stub catches the main agent *and* every
    # subagent's model lookup.
    monkeypatch.setattr("quoriv.core.agent.get_model", lambda _model_id: stub)
    monkeypatch.setattr("quoriv.core.subagents.get_model", lambda _model_id: stub)

    config = QuorivConfig.model_validate({})
    return build_agent(
        config,
        cwd=tmp_path,
        mode="yolo",  # disables HITL interrupts → one-shot model turn
        checkpointer=MemorySaver(),
    )


# ---------------------------------------------------------------------------
# End-to-end turn pipeline
# ---------------------------------------------------------------------------


class TestEndToEndTurn:
    async def test_drive_turn_writes_turn_start_and_end(
        self,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        agent = _make_stub_agent(monkeypatch, tmp_path)
        tracer = TraceLogger(trace_path(tmp_path, "thread-int-1"))
        console, _buf = _stub_console()

        await _drive_turn(
            console,
            agent,
            "what is 2+2?",
            "thread-int-1",
            "yolo",
            tracer=tracer,
        )

        events = _read_trace(tracer.path)
        kinds = [e["event"] for e in events]
        # The bracketing pair must be present — that's the contract
        # /cost and any future observability tooling depend on.
        assert kinds[0] == "turn_start"
        assert kinds[-1] == "turn_end"

        start = events[0]
        assert start["thread_id"] == "thread-int-1"
        assert start["user_input"] == "what is 2+2?"
        assert start["mode"] == "yolo"

        end = events[-1]
        assert end["thread_id"] == "thread-int-1"

    async def test_drive_turn_records_model_complete(
        self,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        agent = _make_stub_agent(monkeypatch, tmp_path)
        tracer = TraceLogger(trace_path(tmp_path, "thread-int-2"))
        console, _buf = _stub_console()

        await _drive_turn(
            console,
            agent,
            "hi",
            "thread-int-2",
            "yolo",
            tracer=tracer,
        )

        events = _read_trace(tracer.path)
        model_completes = [e for e in events if e["event"] == "model_complete"]
        # The stub emits one AIMessage → one on_chat_model_end →
        # one model_complete record.
        assert len(model_completes) >= 1

    async def test_drive_turn_renders_stub_response(
        self,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        # Sanity that the stream wiring actually emits the model text to
        # the console — not just that the trace bracket is intact.
        agent = _make_stub_agent(monkeypatch, tmp_path, response="ABCDE-stub-payload")
        tracer = TraceLogger(trace_path(tmp_path, "thread-int-3"))
        console, buf = _stub_console()

        await _drive_turn(
            console,
            agent,
            "say hi",
            "thread-int-3",
            "yolo",
            tracer=tracer,
        )

        # Don't pin exact formatting — Rich's Live may emit extra
        # whitespace or paint chunks. Just confirm the payload made it
        # through the StreamRenderer to the console buffer.
        assert "ABCDE-stub-payload" in buf.getvalue()

    async def test_status_line_built_from_session_context(
        self,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        # The status line is built from the same context the chat loop
        # carries through a turn (model_id / mode / cwd / thread_id).
        # Drive a turn end-to-end first, then verify the builder still
        # returns a well-formed string for the same context — i.e. no
        # interaction with mid-flight agent state can corrupt it.
        agent = _make_stub_agent(monkeypatch, tmp_path)
        tracer = TraceLogger(trace_path(tmp_path, "thread-int-status"))
        console, _buf = _stub_console()

        await _drive_turn(
            console,
            agent,
            "noop",
            "thread-int-status",
            "yolo",
            tracer=tracer,
        )

        line = _build_status_line(
            model_id="openai:gpt-5",
            mode="yolo",
            cwd=tmp_path,
            thread_id="thread-int-status",
        )
        assert "openai:gpt-5" in line
        assert "mode=yolo" in line
        # First 8 chars of the thread id appear; the full id does not.
        assert "thread-i" in line
        assert "thread-int-status" not in line
        # Status line has 3 separators (4 fields).
        assert line.count("|") == 3
