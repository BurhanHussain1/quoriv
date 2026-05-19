"""Eval harness — Phase 3 Slice 13, Phase 4 Slice 2.

A tiny regression-catcher for the agent. Each :class:`EvalCase`
describes one prompt to send and a list of substrings the agent's
final response must contain. :func:`score_case` is a pure function
that takes a case + an output string and returns an
:class:`EvalResult` summarising what passed and what didn't.

The substring assertion is intentionally loose — LLM outputs vary
between runs and tighter exact-match checks would be flaky. Use
distinctive tokens that are very unlikely to appear by chance
(``"DIVIDE BY ZERO"``, ``"src/main.py:42"``) rather than common
English.

Phase 4 Slice 2 added :func:`run_case` and :func:`run_suite` — the
runtime that drives each case through ``_drive_turn`` against a
configured agent and extracts the final assistant text for scoring.
``quoriv eval`` in :mod:`quoriv.cli` exposes the suite runner from
the command line.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quoriv.config import QuorivConfig
    from quoriv.permissions import PermissionMode


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One eval prompt + its assertions.

    Attributes:
        name: Human-readable case identifier (used in result tables).
        prompt: The user prompt sent to the agent.
        expected_substrings: Each string must appear in the agent's
            final response for the case to pass. Matching is
            case-sensitive and unanchored.
    """

    name: str
    prompt: str
    expected_substrings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvalResult:
    """The outcome of one scored case.

    Attributes:
        case_name: Mirrors :attr:`EvalCase.name`.
        passed: ``True`` iff every expected substring appeared in
            the output.
        failed_substrings: Substrings the output was missing.
            Empty when ``passed`` is True.
        output: The raw output that was scored. Truncated by the
            caller if needed before storage.
    """

    case_name: str
    passed: bool
    failed_substrings: tuple[str, ...]
    output: str


def score_case(case: EvalCase, output: str) -> EvalResult:
    """Score one case against the agent's final output.

    A case with no expected substrings always passes — useful for
    smoke tests where you only care that the agent didn't error.

    Args:
        case: The case definition.
        output: The agent's final response text.

    Returns:
        :class:`EvalResult` describing pass / fail and which
        substrings (if any) the output was missing.
    """
    missing = tuple(s for s in case.expected_substrings if s not in output)
    return EvalResult(
        case_name=case.name,
        passed=not missing,
        failed_substrings=missing,
        output=output,
    )


def summarize(results: list[EvalResult]) -> dict[str, int]:
    """Aggregate counts across a list of results.

    Args:
        results: Output of running :func:`score_case` over each case.

    Returns:
        ``{"total": int, "passed": int, "failed": int}``.
    """
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {"total": total, "passed": passed, "failed": total - passed}


# ---------------------------------------------------------------------------
# Bundled sample cases
# ---------------------------------------------------------------------------


SAMPLE_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        name="echo-phrase",
        prompt='Respond with exactly the phrase "QUORIV_EVAL_OK" and nothing else.',
        expected_substrings=("QUORIV_EVAL_OK",),
    ),
    EvalCase(
        name="basic-arithmetic",
        prompt="What is 17 multiplied by 23? Include the number in your answer.",
        expected_substrings=("391",),
    ),
    EvalCase(
        name="code-citation-format",
        # Format-only assertion; we don't care if the agent fabricates
        # a function name, only that it uses the file:line shape.
        prompt=(
            "Pretend a bug lives in src/main.py on line 42. Mention it "
            "using the conventional 'file:line' format."
        ),
        expected_substrings=("src/main.py:42",),
    ),
)
"""Three minimal sanity cases for regression catching.

The substrings are distinctive enough (a custom token, a specific
number, a path:line combination) that random LLM drift is very
unlikely to satisfy them by accident. A regression that breaks the
agent's ability to follow basic instructions will fail at least one.
"""


def passed_fraction(results: list[EvalResult]) -> float:
    """Return passed / total as a float in ``[0.0, 1.0]``.

    Empty result lists return ``1.0`` (vacuously) — a CI script
    treating "no cases" as a regression would have been the wrong
    invariant anyway.
    """
    if not results:
        return 1.0
    return summarize(results)["passed"] / summarize(results)["total"]


# ---------------------------------------------------------------------------
# Runner — Phase 4 Slice 2
# ---------------------------------------------------------------------------


def _final_ai_text(messages: list[Any]) -> str:
    """Pull the last assistant text out of a LangGraph message list.

    Walks the list in reverse looking for an ``AIMessage`` with
    non-empty string ``content``. ``AIMessage.content`` is sometimes a
    list of dict chunks (provider-dependent); when that happens we
    concatenate any ``"text"`` fields. Returns an empty string if no
    suitable message is found — :func:`score_case` will then report
    every expected substring as missing.
    """
    from langchain_core.messages import AIMessage  # noqa: PLC0415  (intentional lazy import)

    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str):
            if content:
                return content
            continue
        if isinstance(content, list):
            parts = [
                chunk.get("text", "")
                for chunk in content
                if isinstance(chunk, dict) and chunk.get("type") in (None, "text")
            ]
            joined = "".join(parts)
            if joined:
                return joined
    return ""


async def run_case(
    case: EvalCase,
    *,
    config: QuorivConfig | None = None,
    cwd: Path | None = None,
    mode: PermissionMode = "yolo",
    model_override: str | None = None,
    agent: Any | None = None,
) -> EvalResult:
    """Run one eval case end-to-end and score the agent's final output.

    Drives ``case.prompt`` through :func:`quoriv.app._drive_turn`
    against a fresh agent (or a caller-supplied ``agent``), then pulls
    the latest assistant text out of the LangGraph state and feeds it
    to :func:`score_case`.

    Args:
        case: The case definition.
        config: Loaded Quoriv config. Required when ``agent`` is
            ``None`` so the runner can build one.
        cwd: Working directory for the agent's filesystem + shell.
            Defaults to ``Path.cwd()``. Ignored when ``agent`` is
            supplied.
        mode: Permission mode — defaults to ``"yolo"`` so eval cases
            run unattended. Pass ``"ask"`` or ``"auto"`` only if the
            caller is wiring its own approval prompts.
        model_override: ``provider:name`` override for the agent's
            default model. Ignored when ``agent`` is supplied.
        agent: Optional pre-built agent. Useful for tests that inject
            a stubbed LLM. When ``None``, a fresh agent is built with
            an in-memory checkpointer.

    Returns:
        The scored :class:`EvalResult`.

    Raises:
        ValueError: If neither ``config`` nor ``agent`` is provided.
    """
    # Lazy imports — keep ``quoriv.eval`` importable for the pure
    # scoring layer without pulling DeepAgents / LangGraph in.
    from langgraph.checkpoint.memory import MemorySaver  # noqa: PLC0415
    from rich.console import Console  # noqa: PLC0415

    from quoriv.app import _drive_turn  # noqa: PLC0415
    from quoriv.core import build_agent  # noqa: PLC0415

    if agent is None:
        if config is None:
            raise ValueError("run_case requires either `config` (to build an agent) or `agent`.")
        agent = build_agent(
            config,
            model_override=model_override,
            cwd=cwd if cwd is not None else Path.cwd(),
            mode=mode,
            checkpointer=MemorySaver(),
        )

    # Per-case thread id so cases never share checkpointer state.
    thread_id = f"eval-{case.name}"
    # Eval runs quiet — discard the rendered stream to an in-memory
    # buffer. ``force_terminal=False`` keeps ``rich.live.Live`` from
    # repainting the real terminal.
    sink = Console(file=StringIO(), width=10_000, force_terminal=False, no_color=True)

    await _drive_turn(sink, agent, case.prompt, thread_id, mode)

    state = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    messages = state.values.get("messages", []) if hasattr(state, "values") else []
    final_text = _final_ai_text(messages)
    return score_case(case, final_text)


async def run_suite(
    cases: tuple[EvalCase, ...] | list[EvalCase],
    *,
    config: QuorivConfig | None = None,
    cwd: Path | None = None,
    mode: PermissionMode = "yolo",
    model_override: str | None = None,
    agent: Any | None = None,
) -> list[EvalResult]:
    """Run a suite of cases sequentially and return their results.

    Each case runs through :func:`run_case` with the same agent /
    config. A per-case exception is captured as a failed
    :class:`EvalResult` (output is the exception text, every expected
    substring is marked missing) so one bad case can't poison the
    rest of the run.

    Case order is preserved in the returned list.
    """
    results: list[EvalResult] = []
    for case in cases:
        try:
            results.append(
                await run_case(
                    case,
                    config=config,
                    cwd=cwd,
                    mode=mode,
                    model_override=model_override,
                    agent=agent,
                )
            )
        except Exception as exc:
            results.append(
                EvalResult(
                    case_name=case.name,
                    passed=False,
                    failed_substrings=case.expected_substrings,
                    output=f"<error: {type(exc).__name__}: {exc}>",
                )
            )
    return results
