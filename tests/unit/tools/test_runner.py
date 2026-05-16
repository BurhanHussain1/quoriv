"""Tests for `quoriv.tools.tests` (the `run_tests` tool).

We test the framework-detection + command-building pure functions
directly against fake project layouts, then exercise the full
``run_tests`` path with subprocess mocked so the test suite does not
shell out to ``pytest`` / ``cargo`` / ``npm`` / ``go`` (which may or
may not be installed on a contributor's machine).

There is one integration-style test that *does* invoke real subprocess:
it points ``run_tests`` at a directory with a trivial fake binary on
``PATH`` to verify the binary-not-found error shape.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from quoriv.tools import QUORIV_TOOLS
from quoriv.tools.tests import (
    _build_command,
    _detect_framework,
    _parse_pytest_summary,
    run_tests,
)

# ---------------------------------------------------------------------------
# _detect_framework
# ---------------------------------------------------------------------------


class TestDetectFramework:
    def test_pyproject_toml_means_pytest(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        assert _detect_framework(tmp_path) == "pytest"

    def test_pytest_ini_means_pytest(self, tmp_path: Path) -> None:
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        assert _detect_framework(tmp_path) == "pytest"

    def test_setup_cfg_means_pytest(self, tmp_path: Path) -> None:
        (tmp_path / "setup.cfg").write_text("[metadata]\nname=x\n", encoding="utf-8")
        assert _detect_framework(tmp_path) == "pytest"

    def test_package_json_means_npm(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "x"}', encoding="utf-8")
        assert _detect_framework(tmp_path) == "npm"

    def test_cargo_toml_means_cargo(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        assert _detect_framework(tmp_path) == "cargo"

    def test_go_mod_means_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
        assert _detect_framework(tmp_path) == "go"

    def test_empty_dir_returns_none(self, tmp_path: Path) -> None:
        assert _detect_framework(tmp_path) is None

    def test_python_wins_over_node_in_polyglot(self, tmp_path: Path) -> None:
        # Order matters: pyproject.toml is checked before package.json so a
        # polyglot repo defaults to Python — match the layout of Quoriv itself.
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (tmp_path / "package.json").write_text('{"name": "x"}', encoding="utf-8")
        assert _detect_framework(tmp_path) == "pytest"


# ---------------------------------------------------------------------------
# _build_command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_pytest_default(self) -> None:
        assert _build_command("pytest", None) == ["pytest", "-q"]

    def test_pytest_with_path(self) -> None:
        assert _build_command("pytest", "tests/unit") == ["pytest", "-q", "tests/unit"]

    def test_npm_default(self) -> None:
        assert _build_command("npm", None) == ["npm", "test", "--silent"]

    def test_npm_with_path(self) -> None:
        assert _build_command("npm", "src/foo.test.js") == [
            "npm",
            "test",
            "--silent",
            "--",
            "src/foo.test.js",
        ]

    def test_cargo_default(self) -> None:
        assert _build_command("cargo", None) == ["cargo", "test"]

    def test_cargo_with_path(self) -> None:
        assert _build_command("cargo", "my_test") == ["cargo", "test", "--", "my_test"]

    def test_go_default_uses_recursive_selector(self) -> None:
        assert _build_command("go", None) == ["go", "test", "./..."]

    def test_go_with_path_replaces_selector(self) -> None:
        assert _build_command("go", "./pkg/foo") == ["go", "test", "./pkg/foo"]

    def test_unknown_framework_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown framework"):
            _build_command("rspec", None)


# ---------------------------------------------------------------------------
# Slice 6b — _parse_pytest_summary
# ---------------------------------------------------------------------------


class TestParsePytestSummary:
    def test_passing_only(self) -> None:
        result = _parse_pytest_summary("============= 12 passed in 0.34s =============")
        assert result == {
            "passed": 12,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration_seconds": 0.34,
        }

    def test_failed_only(self) -> None:
        result = _parse_pytest_summary("==== 1 failed in 0.05s ====")
        assert result["failed"] == 1
        assert result["passed"] == 0
        assert result["duration_seconds"] == 0.05

    def test_mixed_passed_failed_errors(self) -> None:
        result = _parse_pytest_summary("==== 5 passed, 2 failed, 1 error in 1.20s ====")
        assert result["passed"] == 5
        assert result["failed"] == 2
        assert result["errors"] == 1
        assert result["duration_seconds"] == 1.2

    def test_passed_and_skipped(self) -> None:
        result = _parse_pytest_summary("==== 3 passed, 1 skipped in 0.50s ====")
        assert result["passed"] == 3
        assert result["skipped"] == 1
        assert result["failed"] == 0

    def test_no_tests_ran(self) -> None:
        # "no tests ran in 0.01s" — every count stays 0, duration is captured.
        result = _parse_pytest_summary("==== no tests ran in 0.01s ====")
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert result["duration_seconds"] == 0.01

    def test_plural_errors(self) -> None:
        # pytest emits "errors" (plural) when N > 1.
        result = _parse_pytest_summary("==== 3 errors in 0.10s ====")
        assert result["errors"] == 3

    def test_no_summary_returns_all_none(self) -> None:
        result = _parse_pytest_summary("collected 0 items\n\n=== there is no summary ===")
        assert result == {
            "passed": None,
            "failed": None,
            "errors": None,
            "skipped": None,
            "duration_seconds": None,
        }

    def test_empty_output_returns_all_none(self) -> None:
        result = _parse_pytest_summary("")
        assert all(v is None for v in result.values())

    def test_uses_last_match_when_multiple(self) -> None:
        # Pytest can emit multiple "=" separator lines during a run; only the
        # final summary line (with the duration suffix) counts.
        output = "===== test session starts =====\ncollected 3 items\n==== 3 passed in 0.10s ===="
        result = _parse_pytest_summary(output)
        assert result["passed"] == 3


# ---------------------------------------------------------------------------
# run_tests — full path with subprocess mocked.
# ---------------------------------------------------------------------------


def _fake_completed(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fake"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestRunTests:
    def _patch_subprocess(
        self,
        monkeypatch: pytest.MonkeyPatch,
        result: subprocess.CompletedProcess[str] | None = None,
        *,
        raise_file_not_found: bool = False,
    ) -> list[dict[str, Any]]:
        """Patch ``subprocess.run`` and record each call's kwargs.

        Returns a list that callers can inspect for command / cwd assertions.
        """
        calls: list[dict[str, Any]] = []

        def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append({"args": args, **kwargs})
            if raise_file_not_found:
                raise FileNotFoundError("fake: not on PATH")
            return result if result is not None else _fake_completed()

        monkeypatch.setattr("quoriv.tools.tests.subprocess.run", fake_run)
        return calls

    def test_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        self._patch_subprocess(
            monkeypatch,
            _fake_completed(returncode=0, stdout="5 passed", stderr=""),
        )
        result = run_tests.invoke({"cwd": str(tmp_path)})
        assert result["framework"] == "pytest"
        assert result["command"] == ["pytest", "-q"]
        assert result["exit_code"] == 0
        assert result["passed"] is True
        assert result["stdout"] == "5 passed"

    def test_failure_sets_passed_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        self._patch_subprocess(
            monkeypatch,
            _fake_completed(returncode=1, stdout="1 failed", stderr=""),
        )
        result = run_tests.invoke({"cwd": str(tmp_path)})
        assert result["exit_code"] == 1
        assert result["passed"] is False

    def test_framework_override(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Empty dir → no auto-detect, but framework= override should still work.
        calls = self._patch_subprocess(monkeypatch)
        result = run_tests.invoke({"framework": "cargo", "cwd": str(tmp_path)})
        assert result["framework"] == "cargo"
        assert calls[0]["args"] == ["cargo", "test"]

    def test_path_scoping_pytest(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        calls = self._patch_subprocess(monkeypatch)
        run_tests.invoke({"path": "tests/unit", "cwd": str(tmp_path)})
        assert calls[0]["args"] == ["pytest", "-q", "tests/unit"]

    def test_no_framework_detected(self, tmp_path: Path) -> None:
        result = run_tests.invoke({"cwd": str(tmp_path)})
        assert "error" in result
        assert "no test framework detected" in result["error"]

    def test_unknown_framework_override(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        result = run_tests.invoke({"framework": "rspec", "cwd": str(tmp_path)})
        assert "error" in result
        assert "Unknown framework" in result["error"]

    def test_nonexistent_cwd(self, tmp_path: Path) -> None:
        result = run_tests.invoke({"cwd": str(tmp_path / "does-not-exist")})
        assert "error" in result
        assert "cwd does not exist" in result["error"]

    def test_runner_binary_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        self._patch_subprocess(monkeypatch, raise_file_not_found=True)
        result = run_tests.invoke({"cwd": str(tmp_path)})
        assert "error" in result
        assert "cargo runner binary not found" in result["error"]
        # Even on error we surface what we tried to run so the agent can adapt.
        assert result["framework"] == "cargo"
        assert result["command"] == ["cargo", "test"]

    def test_subprocess_invoked_with_resolved_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        calls = self._patch_subprocess(monkeypatch)
        run_tests.invoke({"cwd": str(tmp_path)})
        assert Path(calls[0]["cwd"]) == tmp_path.resolve()

    def test_subprocess_runs_with_shell_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # We construct the call via positional args + kwargs — verify there is
        # no shell=True leaking through. (The implementation passes args as a
        # list and never sets shell=, so the kwargs we capture should omit it.)
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        calls = self._patch_subprocess(monkeypatch)
        run_tests.invoke({"cwd": str(tmp_path)})
        assert "shell" not in calls[0]

    # ----- Slice 6b: parsed pytest counts -----------------------------------

    def test_pytest_summary_surfaces_counts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        self._patch_subprocess(
            monkeypatch,
            _fake_completed(
                returncode=1,
                stdout="==== 5 passed, 2 failed, 1 error in 1.20s ====\n",
                stderr="",
            ),
        )
        result = run_tests.invoke({"cwd": str(tmp_path)})
        summary = result["summary"]
        assert summary["passed"] == 5
        assert summary["failed"] == 2
        assert summary["errors"] == 1
        assert summary["skipped"] == 0
        assert summary["duration_seconds"] == 1.2

    def test_pytest_summary_in_stderr_is_still_parsed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Some CI environments redirect pytest's terminal output via stderr.
        # Parser reads stdout + stderr concatenated.
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        self._patch_subprocess(
            monkeypatch,
            _fake_completed(
                returncode=0,
                stdout="",
                stderr="==== 7 passed in 0.42s ====\n",
            ),
        )
        result = run_tests.invoke({"cwd": str(tmp_path)})
        assert result["summary"]["passed"] == 7

    def test_pytest_with_no_summary_line_returns_null_counts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # If pytest crashed before emitting a summary (e.g., collection error),
        # the summary fields remain None so the agent can tell "couldn't parse"
        # from "0 passed".
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        self._patch_subprocess(
            monkeypatch,
            _fake_completed(returncode=2, stdout="ImportError: ...", stderr=""),
        )
        result = run_tests.invoke({"cwd": str(tmp_path)})
        assert result["summary"]["passed"] is None
        assert result["summary"]["duration_seconds"] is None

    def test_non_pytest_framework_has_null_summary(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Slice 6b only parses pytest. Cargo / go / npm get the placeholder
        # all-None summary until Slice 6c lands their parsers.
        self._patch_subprocess(
            monkeypatch,
            _fake_completed(returncode=0, stdout="ok blah blah", stderr=""),
        )
        result = run_tests.invoke({"framework": "cargo", "cwd": str(tmp_path)})
        assert result["summary"] == {
            "passed": None,
            "failed": None,
            "errors": None,
            "skipped": None,
            "duration_seconds": None,
        }


# ---------------------------------------------------------------------------
# Tool registration.
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_is_langchain_tool(self) -> None:
        assert hasattr(run_tests, "invoke")
        assert hasattr(run_tests, "name")
        assert run_tests.name == "run_tests"

    def test_in_quoriv_tools(self) -> None:
        names = {t.name for t in QUORIV_TOOLS}
        assert "run_tests" in names
