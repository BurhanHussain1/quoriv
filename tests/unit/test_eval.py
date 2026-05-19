"""Tests for ``quoriv.eval`` — Phase 3 Slice 13."""

from __future__ import annotations

from quoriv.eval import (
    SAMPLE_CASES,
    EvalCase,
    EvalResult,
    passed_fraction,
    score_case,
    summarize,
)


class TestScoreCase:
    def test_all_substrings_present_passes(self) -> None:
        case = EvalCase(name="x", prompt="?", expected_substrings=("hello", "world"))
        result = score_case(case, "hello there, world!")
        assert result.passed is True
        assert result.failed_substrings == ()
        assert result.case_name == "x"
        assert result.output == "hello there, world!"

    def test_missing_substring_fails(self) -> None:
        case = EvalCase(name="x", prompt="?", expected_substrings=("found", "absent"))
        result = score_case(case, "found this; nothing else")
        assert result.passed is False
        assert result.failed_substrings == ("absent",)

    def test_case_sensitive(self) -> None:
        # "Hello" != "hello" — keep matching strict so a model that
        # case-drifts away from a required token gets flagged.
        case = EvalCase(name="x", prompt="?", expected_substrings=("Hello",))
        assert score_case(case, "hello world").passed is False
        assert score_case(case, "Hello world").passed is True

    def test_empty_expectations_always_pass(self) -> None:
        # Smoke-test mode — only care that the agent didn't crash.
        case = EvalCase(name="smoke", prompt="hi", expected_substrings=())
        assert score_case(case, "any output at all").passed is True
        assert score_case(case, "").passed is True

    def test_substring_not_anchored(self) -> None:
        # Substring match, not exact / prefix / suffix.
        case = EvalCase(name="x", prompt="?", expected_substrings=("middle",))
        assert score_case(case, "start middle end").passed is True


class TestSummarize:
    def test_empty_zero(self) -> None:
        assert summarize([]) == {"total": 0, "passed": 0, "failed": 0}

    def test_all_passing(self) -> None:
        results = [
            EvalResult("a", True, (), "x"),
            EvalResult("b", True, (), "y"),
        ]
        assert summarize(results) == {"total": 2, "passed": 2, "failed": 0}

    def test_mixed(self) -> None:
        results = [
            EvalResult("a", True, (), "x"),
            EvalResult("b", False, ("missing",), "y"),
            EvalResult("c", True, (), "z"),
        ]
        assert summarize(results) == {"total": 3, "passed": 2, "failed": 1}


class TestPassedFraction:
    def test_empty_is_one(self) -> None:
        # Vacuous: no cases means "no failures observed".
        assert passed_fraction([]) == 1.0

    def test_all_passing_is_one(self) -> None:
        results = [EvalResult("a", True, (), "x")]
        assert passed_fraction(results) == 1.0

    def test_all_failing_is_zero(self) -> None:
        results = [EvalResult("a", False, ("m",), "x")]
        assert passed_fraction(results) == 0.0

    def test_half_passing(self) -> None:
        results = [
            EvalResult("a", True, (), "x"),
            EvalResult("b", False, ("m",), "y"),
        ]
        assert passed_fraction(results) == 0.5


class TestSampleCases:
    def test_bundle_is_non_empty(self) -> None:
        assert len(SAMPLE_CASES) > 0

    def test_each_case_has_name_and_prompt(self) -> None:
        for case in SAMPLE_CASES:
            assert case.name
            assert case.prompt
            # Bundled cases all have at least one expected substring
            # so a regression has something concrete to break.
            assert case.expected_substrings

    def test_case_names_unique(self) -> None:
        # Duplicate names would break result-by-name lookups in any
        # future runner UI.
        names = [c.name for c in SAMPLE_CASES]
        assert len(names) == len(set(names))

    def test_scoring_sample_cases_against_matching_output_passes(self) -> None:
        # Synthesise an output that hits every expected substring
        # for every bundled case — confirms the assertions are
        # satisfiable, not impossible-by-construction.
        for case in SAMPLE_CASES:
            output = " ".join(case.expected_substrings)
            assert score_case(case, output).passed is True
