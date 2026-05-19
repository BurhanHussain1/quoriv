"""Eval harness — Phase 3 Slice 13.

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

This slice ships the **scoring layer** plus a small bundled set of
sanity cases. A future slice wires this into the chat loop so
``quoriv eval`` can run the suite against a chosen model.
"""

from __future__ import annotations

from dataclasses import dataclass


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
