"""Tests for the eval runner + CLI — Phase 4 Slice 2.

The runner is exercised against the same ``GenericFakeChatModel`` stub
used in ``tests/integration/test_e2e_stubbed_chat.py`` — we don't need
a real LLM to verify that ``run_case`` drives a turn, pulls the final
assistant text out of LangGraph state, and feeds it to ``score_case``.

The CLI tests monkeypatch ``run_suite`` directly so they assert the
plumbing (table render, exit code, ``--model`` forwarding) without
paying for the agent build.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from typer.testing import CliRunner

from quoriv import app as quoriv_app
from quoriv.cli import app
from quoriv.config.schema import QuorivConfig
from quoriv.core import build_agent
from quoriv.eval import (
    EvalCase,
    EvalResult,
    _final_ai_text,
    run_case,
    run_suite,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


class _StubChatModel(GenericFakeChatModel):
    """``GenericFakeChatModel`` whose ``bind_tools`` returns ``self``.

    Mirrors the helper in ``tests/integration/test_e2e_stubbed_chat.py``
    — DeepAgents binds tools to the model at compile time, and the
    upstream fake raises ``NotImplementedError`` for ``bind_tools``.
    """

    def bind_tools(self, _tools: Any, **_kwargs: Any) -> Any:  # type: ignore[override]
        return self


def _make_stub_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    response: str = "QUORIV_EVAL_OK and 391 and src/main.py:42",
    repeats: int = 16,
) -> Any:
    """Build a real Quoriv agent with the LLM swapped for a stub."""
    msgs = iter([AIMessage(content=response) for _ in range(repeats)])
    stub = _StubChatModel(messages=msgs)
    monkeypatch.setattr("quoriv.core.agent.get_model", lambda _model_id: stub)
    monkeypatch.setattr("quoriv.core.subagents.get_model", lambda _model_id: stub)

    cfg = QuorivConfig.model_validate({})
    checkpointer: BaseCheckpointSaver[Any] = MemorySaver()
    return build_agent(cfg, cwd=tmp_path, mode="yolo", checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# _final_ai_text — pure helper
# ---------------------------------------------------------------------------


class TestFinalAIText:
    def test_returns_str_content_of_last_ai_message(self) -> None:
        messages = [AIMessage(content="first"), AIMessage(content="last")]
        assert _final_ai_text(messages) == "last"

    def test_skips_empty_ai_messages(self) -> None:
        # Empty content earlier in the list shouldn't shadow a real reply.
        messages = [AIMessage(content="real"), AIMessage(content="")]
        assert _final_ai_text(messages) == "real"

    def test_joins_list_content_chunks(self) -> None:
        # Some providers (Anthropic) return content as a list of dict chunks.
        chunks = [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}]
        messages = [AIMessage(content=chunks)]
        assert _final_ai_text(messages) == "hello world"

    def test_returns_empty_when_no_ai_message(self) -> None:
        # No AIMessage at all — runner will report every substring as missing.
        messages = [HumanMessage(content="hi")]
        assert _final_ai_text(messages) == ""

    def test_returns_empty_for_empty_list(self) -> None:
        assert _final_ai_text([]) == ""


# ---------------------------------------------------------------------------
# run_case — end-to-end against the stubbed agent
# ---------------------------------------------------------------------------


class TestRunCase:
    async def test_passing_case_returns_passed_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        agent = _make_stub_agent(monkeypatch, tmp_path, response="here is QUORIV_EVAL_OK for you")
        case = EvalCase(name="echo", prompt="say it", expected_substrings=("QUORIV_EVAL_OK",))
        result = await run_case(case, agent=agent)
        assert result.passed is True
        assert result.case_name == "echo"
        assert result.failed_substrings == ()
        assert "QUORIV_EVAL_OK" in result.output

    async def test_failing_case_reports_missing_substrings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        agent = _make_stub_agent(monkeypatch, tmp_path, response="nothing relevant here")
        case = EvalCase(
            name="miss",
            prompt="say it",
            expected_substrings=("QUORIV_EVAL_OK", "alpha"),
        )
        result = await run_case(case, agent=agent)
        assert result.passed is False
        assert result.failed_substrings == ("QUORIV_EVAL_OK", "alpha")

    async def test_uses_per_case_thread_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Two cases against the same agent should not bleed checkpointer state.
        # We verify this indirectly by checking the agent's state for the
        # case-derived thread id.
        agent = _make_stub_agent(monkeypatch, tmp_path, response="ok")
        case = EvalCase(name="alpha", prompt="hi", expected_substrings=())
        await run_case(case, agent=agent)
        state = await agent.aget_state({"configurable": {"thread_id": "eval-alpha"}})
        assert state.values.get("messages")

    async def test_requires_config_or_agent(self) -> None:
        case = EvalCase(name="x", prompt="hi", expected_substrings=())
        with pytest.raises(ValueError, match="config"):
            await run_case(case)

    async def test_smoke_case_passes_with_no_expected_substrings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # A case with no expected substrings is a smoke test — it
        # passes as long as the runner drives a turn without erroring.
        agent = _make_stub_agent(monkeypatch, tmp_path, response="anything at all")
        case = EvalCase(name="smoke", prompt="hi", expected_substrings=())
        result = await run_case(case, agent=agent)
        assert result.passed is True
        assert result.case_name == "smoke"


# ---------------------------------------------------------------------------
# run_suite — multi-case sequencing + per-case isolation
# ---------------------------------------------------------------------------


class TestRunSuite:
    async def test_returns_one_result_per_case_in_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        agent = _make_stub_agent(monkeypatch, tmp_path, response="payload-XYZ")
        cases = (
            EvalCase(name="a", prompt="hi", expected_substrings=("XYZ",)),
            EvalCase(name="b", prompt="hi", expected_substrings=("XYZ",)),
            EvalCase(name="c", prompt="hi", expected_substrings=("MISS",)),
        )
        results = await run_suite(cases, agent=agent)
        assert [r.case_name for r in results] == ["a", "b", "c"]
        assert [r.passed for r in results] == [True, True, False]

    async def test_isolates_per_case_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        agent = _make_stub_agent(monkeypatch, tmp_path, response="ok-with-XYZ")
        cases = [EvalCase(name="good", prompt="hi", expected_substrings=("XYZ",))]

        # Synthesise a second case that will blow up inside run_case by
        # stubbing _drive_turn to raise. The first case should still pass.
        call_count = {"n": 0}
        original_drive_turn = quoriv_app._drive_turn

        async def flaky_drive_turn(*args: Any, **kwargs: Any) -> None:
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom")
            await original_drive_turn(*args, **kwargs)

        monkeypatch.setattr(quoriv_app, "_drive_turn", flaky_drive_turn)
        cases.append(EvalCase(name="bad", prompt="hi", expected_substrings=("XYZ",)))

        results = await run_suite(tuple(cases), agent=agent)
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False
        assert results[1].case_name == "bad"
        assert "boom" in results[1].output
        # Failed case still lists every expected substring as missing.
        assert results[1].failed_substrings == ("XYZ",)

    async def test_empty_suite_returns_empty_list(self) -> None:
        results = await run_suite(())
        assert results == []


# ---------------------------------------------------------------------------
# CLI: `quoriv eval`
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestEvalCLI:
    def test_zero_exit_when_all_pass(
        self,
        runner: CliRunner,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_run_suite(*_args: Any, **_kwargs: Any) -> list[EvalResult]:
            return [
                EvalResult(case_name="a", passed=True, failed_substrings=(), output="ok"),
                EvalResult(case_name="b", passed=True, failed_substrings=(), output="ok"),
            ]

        monkeypatch.setattr("quoriv.eval.run_suite", fake_run_suite)
        result = runner.invoke(app, ["eval"])
        assert result.exit_code == 0
        assert "2/2" in result.stdout
        assert "pass" in result.stdout

    def test_nonzero_exit_when_any_fail(
        self,
        runner: CliRunner,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_run_suite(*_args: Any, **_kwargs: Any) -> list[EvalResult]:
            return [
                EvalResult(case_name="a", passed=True, failed_substrings=(), output="ok"),
                EvalResult(case_name="b", passed=False, failed_substrings=("XYZ",), output=""),
            ]

        monkeypatch.setattr("quoriv.eval.run_suite", fake_run_suite)
        result = runner.invoke(app, ["eval"])
        assert result.exit_code == 1
        assert "1/2" in result.stdout
        # The missing substring is rendered in the table.
        assert "XYZ" in result.stdout

    def test_renders_case_names_in_table(
        self,
        runner: CliRunner,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_run_suite(*_args: Any, **_kwargs: Any) -> list[EvalResult]:
            return [
                EvalResult(case_name="alpha", passed=True, failed_substrings=(), output="ok"),
                EvalResult(case_name="beta", passed=False, failed_substrings=("Q",), output=""),
            ]

        monkeypatch.setattr("quoriv.eval.run_suite", fake_run_suite)
        result = runner.invoke(app, ["eval"])
        assert "alpha" in result.stdout
        assert "beta" in result.stdout

    def test_forwards_model_override(
        self,
        runner: CliRunner,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        async def fake_run_suite(*_args: Any, **kwargs: Any) -> list[EvalResult]:
            captured.update(kwargs)
            return [EvalResult(case_name="x", passed=True, failed_substrings=(), output="ok")]

        monkeypatch.setattr("quoriv.eval.run_suite", fake_run_suite)
        result = runner.invoke(app, ["eval", "--model", "openai:gpt-5"])
        assert result.exit_code == 0
        assert captured.get("model_override") == "openai:gpt-5"

    def test_forwards_cwd(
        self,
        runner: CliRunner,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        captured: dict[str, Any] = {}

        async def fake_run_suite(*_args: Any, **kwargs: Any) -> list[EvalResult]:
            captured.update(kwargs)
            return [EvalResult(case_name="x", passed=True, failed_substrings=(), output="ok")]

        monkeypatch.setattr("quoriv.eval.run_suite", fake_run_suite)
        result = runner.invoke(app, ["eval", "--cwd", str(tmp_path)])
        assert result.exit_code == 0
        # Path resolution may canonicalize, so compare resolved forms.
        assert Path(str(captured.get("cwd"))).resolve() == tmp_path.resolve()
