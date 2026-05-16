"""Language-aware test runner — Phase 1 Slice 6.

Single ``@tool`` callable :func:`run_tests` that auto-detects the
project's test framework by looking for marker files in ``cwd``:

    pyproject.toml | pytest.ini | setup.cfg   →   pytest
    package.json                              →   npm test
    Cargo.toml                                →   cargo test
    go.mod                                    →   go test ./...

The agent can override the auto-detection by passing ``framework=`` and
can scope to a sub-path with ``path=``. Output is returned as structured
``dict[str, Any]`` so the LLM does not need to parse free-form runner
output to decide whether the suite passed::

    {
      "framework": str,        # "pytest" / "npm" / "cargo" / "go"
      "command": list[str],    # exact argv invoked (no shell expansion)
      "exit_code": int,
      "passed": bool,          # exit_code == 0
      "stdout": str,
      "stderr": str,
    }

Failure paths set an ``"error"`` key (no test framework detected, no
``cwd``, runner binary missing from ``PATH``, etc.).

We deliberately invoke the runner via :mod:`subprocess` with
``shell=False`` and a list of args — there is no shell expansion of
caller-supplied paths. The user's session permission mode still gates
this tool through DeepAgents' ``execute``-style HITL; Slice 6 keeps
``run_tests`` outside ``GIT_WRITE_TOOLS`` because it runs locally
without mutating repo state.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

Framework = str  # "pytest" | "npm" | "cargo" | "go"

# Marker-file → framework. Order matters: the first matching framework wins
# (pyproject.toml is checked before package.json so a polyglot repo with both
# defaults to Python — matching the layout of `quoriv` itself).
_DETECT_ORDER: tuple[tuple[str, Framework], ...] = (
    ("pyproject.toml", "pytest"),
    ("pytest.ini", "pytest"),
    ("setup.cfg", "pytest"),
    ("package.json", "npm"),
    ("Cargo.toml", "cargo"),
    ("go.mod", "go"),
)


def _detect_framework(cwd: Path) -> Framework | None:
    """Return the framework inferred from marker files in ``cwd``, or ``None``."""
    for marker, framework in _DETECT_ORDER:
        if (cwd / marker).is_file():
            return framework
    return None


def _build_command(framework: Framework, path: str | None) -> list[str]:
    """Build the argv list for ``framework``, optionally scoped to ``path``."""
    if framework == "pytest":
        cmd = ["pytest", "-q"]
        if path is not None:
            cmd.append(path)
        return cmd
    if framework == "npm":
        cmd = ["npm", "test", "--silent"]
        if path is not None:
            cmd.extend(["--", path])
        return cmd
    if framework == "cargo":
        cmd = ["cargo", "test"]
        if path is not None:
            cmd.extend(["--", path])
        return cmd
    if framework == "go":
        cmd = ["go", "test"]
        cmd.append(path if path is not None else "./...")
        return cmd
    raise ValueError(f"Unknown framework: {framework!r}")


@tool
def run_tests(
    framework: str | None = None,
    path: str | None = None,
    cwd: str = ".",
) -> dict[str, Any]:
    """Run the project's test suite in ``cwd`` and return a structured result.

    Args:
        framework: Optional framework override. One of
            ``"pytest"`` / ``"npm"`` / ``"cargo"`` / ``"go"``. When ``None``,
            the framework is auto-detected from marker files in ``cwd``.
        path: Optional sub-path to scope the run to (a test file, directory,
            or package selector). Each framework receives it via its own
            convention — for pytest the path is a positional arg, for
            cargo/npm it is appended after ``--``, for go it replaces
            ``./...``.
        cwd: Path to (or inside) the project. Defaults to the current
            working directory.

    Returns:
        On success::

            {
              "framework": str,
              "command": list[str],
              "exit_code": int,
              "passed": bool,
              "stdout": str,
              "stderr": str,
            }

        On failure: ``{"error": "<message>"}``. Failure cases include
        ``cwd`` not existing, no framework detected (and none supplied),
        an unrecognized override, and the runner binary missing from
        ``PATH``.
    """
    cwd_path = Path(cwd).expanduser().resolve()
    if not cwd_path.is_dir():
        return {"error": f"cwd does not exist or is not a directory: {cwd_path}"}

    chosen: Framework
    if framework is None:
        detected = _detect_framework(cwd_path)
        if detected is None:
            return {
                "error": (
                    "no test framework detected — pass framework= explicitly "
                    "or run from a directory containing pyproject.toml / "
                    "package.json / Cargo.toml / go.mod"
                )
            }
        chosen = detected
    else:
        chosen = framework

    try:
        command = _build_command(chosen, path)
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "error": f"{chosen} runner binary not found on PATH ({exc})",
            "framework": chosen,
            "command": command,
        }

    return {
        "framework": chosen,
        "command": command,
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
