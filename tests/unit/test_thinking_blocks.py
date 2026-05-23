"""Tests for the thinking / reasoning chunk parser (Slice 7).

``_chunk_blocks`` and ``_strip_think_tags`` route reasoning tokens
to the thinking buffer regardless of how the provider exposes them:

* Structured content blocks with ``type="thinking"`` (Anthropic).
* Content blocks with ``type="reasoning"`` (OpenAI Responses API).
* ``additional_kwargs.reasoning_content`` (DeepSeek / Kimi).
* Inline ``<think>...</think>`` tags in plain content (DeepSeek-R1
  in non-Responses mode).
"""

from __future__ import annotations

from typing import Any

from quoriv.app import _chunk_blocks, _chunk_blocks_from_content, _strip_think_tags


class _FakeChunk:
    """Stand-in for a LangChain ``BaseMessageChunk``."""

    def __init__(self, content: Any, additional_kwargs: dict[str, Any] | None = None) -> None:
        self.content = content
        self.additional_kwargs = additional_kwargs or {}


class TestChunkBlocksStructured:
    def test_plain_string_content_is_visible(self) -> None:
        text, thinking = _chunk_blocks(_FakeChunk("hello"), {"in_thinking": False, "carry": ""})
        assert text == "hello"
        assert thinking == ""

    def test_anthropic_thinking_block(self) -> None:
        chunk = _FakeChunk(
            [
                {"type": "thinking", "thinking": "Let me reason about this"},
                {"type": "text", "text": "The answer is 42"},
            ]
        )
        text, thinking = _chunk_blocks(chunk, {"in_thinking": False, "carry": ""})
        assert text == "The answer is 42"
        assert thinking == "Let me reason about this"

    def test_openai_reasoning_block(self) -> None:
        chunk = _FakeChunk(
            [
                {"type": "reasoning", "text": "Working through the constraints"},
                {"type": "text", "text": "Done."},
            ]
        )
        text, thinking = _chunk_blocks(chunk, {"in_thinking": False, "carry": ""})
        assert text == "Done."
        assert thinking == "Working through the constraints"

    def test_deepseek_reasoning_content_kwarg(self) -> None:
        # DeepSeek + Kimi via langchain-openai stuff reasoning into
        # additional_kwargs.reasoning_content.
        chunk = _FakeChunk("answer", additional_kwargs={"reasoning_content": "thought"})
        text, thinking = _chunk_blocks(chunk, {"in_thinking": False, "carry": ""})
        assert text == "answer"
        assert thinking == "thought"


class TestInlineThinkTagParser:
    def test_single_chunk_with_complete_tag(self) -> None:
        state: dict[str, Any] = {"in_thinking": False, "carry": ""}
        visible, thinking = _strip_think_tags("<think>reasoning</think>final", state)
        assert visible == "final"
        assert thinking == "reasoning"
        assert state["in_thinking"] is False

    def test_tag_split_across_chunks(self) -> None:
        # First chunk opens but doesn't close.
        state: dict[str, Any] = {"in_thinking": False, "carry": ""}
        v1, t1 = _strip_think_tags("prefix<think>part1", state)
        assert v1 == "prefix"
        assert t1 == "part1"
        assert state["in_thinking"] is True
        # Second chunk closes mid-stream.
        v2, t2 = _strip_think_tags("part2</think>suffix", state)
        assert v2 == "suffix"
        assert t2 == "part2"
        assert state["in_thinking"] is False

    def test_partial_opening_tag_held_back(self) -> None:
        # ``<thi`` at the end of a chunk shouldn't leak as visible
        # text — it might be the start of a ``<think>`` straddling
        # the boundary.
        state: dict[str, Any] = {"in_thinking": False, "carry": ""}
        v1, _ = _strip_think_tags("visible<thi", state)
        assert v1 == "visible"
        assert state["carry"] == "<thi"
        # Next chunk completes the tag.
        v2, t2 = _strip_think_tags("nk>reasoning</think>done", state)
        assert v2 == "done"
        assert t2 == "reasoning"

    def test_no_tags_passthrough(self) -> None:
        state: dict[str, Any] = {"in_thinking": False, "carry": ""}
        v, t = _strip_think_tags("nothing special here", state)
        assert v == "nothing special here"
        assert t == ""

    def test_chunk_blocks_handles_inline_tag(self) -> None:
        # End-to-end: a plain string with ``<think>`` tags routes
        # the inner text to the thinking buffer.
        state: dict[str, Any] = {"in_thinking": False, "carry": ""}
        chunk = _FakeChunk("Answer: <think>internal</think>42")
        text, thinking = _chunk_blocks(chunk, state)
        assert "Answer:" in text
        assert "42" in text
        assert thinking == "internal"


class TestChunkBlocksFromContentDirect:
    def test_empty_content_returns_empty(self) -> None:
        text, thinking = _chunk_blocks_from_content("", additional_kwargs={})
        assert text == ""
        assert thinking == ""

    def test_mixed_list_with_strings_and_blocks(self) -> None:
        text, thinking = _chunk_blocks_from_content(
            ["bare ", {"type": "text", "text": "hello"}, {"type": "reasoning", "text": "r"}],
            additional_kwargs={},
        )
        assert text == "bare hello"
        assert thinking == "r"
