r"""Regex-aware grep tool for Quoriv (Phase 5 Slice 10).

DeepAgents' built-in ``grep`` is literal substring only — fine for
"find every use of ``def foo``" but useless for patterns like
``def \w+_helper`` or ``^class\s+\w+\(.*Base.*\):``. This module ships
``regex_grep`` as a plain Quoriv tool layered on top of the standard
library: no external dependency, fast enough for repos in the
tens-of-thousands-of-files range.

The tool walks the filesystem starting at ``path`` (default ``"."``),
filters by an optional glob (defaults to ``"**/*"``), compiles the
pattern once, and yields up to ``max_matches`` ``(file, line_no,
text)`` tuples. Binary files are skipped via a content sniff
(non-UTF-8 decode error -> skip).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.tools import tool

if TYPE_CHECKING:
    from collections.abc import Iterator

_DEFAULT_MAX_MATCHES = 200
_DEFAULT_MAX_FILES = 5_000
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",  # Rust
        ".tox",
    }
)


@tool
def regex_grep(
    pattern: str,
    path: str = ".",
    glob: str = "**/*",
    *,
    ignore_case: bool = False,
    max_matches: int = _DEFAULT_MAX_MATCHES,
) -> list[dict[str, str | int]]:
    """Search for a Python regex pattern across files under ``path``.

    Unlike DeepAgents' built-in ``grep`` (literal substring only),
    this accepts a full Python regular expression. Returns a list of
    ``{"path", "line", "text"}`` dicts, capped at ``max_matches``.

    Args:
        pattern: Python regex (uses :mod:`re`). E.g. ``r"def \\w+_test"``,
            ``r"^class\\s+\\w+\\(.*Base.*\\):"``.
        path: Directory to start the search. Defaults to the agent's
            cwd. Must be a directory (file-level search isn't useful
            for a tool — the agent can just ``read_file``).
        glob: Optional :mod:`pathlib`-style glob (e.g. ``"**/*.py"``,
            ``"src/**/*.ts"``). Defaults to ``"**/*"`` (all files).
        ignore_case: When ``True``, compile the pattern with
            ``re.IGNORECASE``.
        max_matches: Hard cap on returned matches so a runaway regex
            doesn't flood the chat. Defaults to 200.

    Returns:
        List of ``{"path": <str>, "line": <int>, "text": <str>}`` dicts.
        Empty list if no matches. The pattern is *not* re-included in
        the result; the agent already has it.
    """
    flags = re.IGNORECASE if ignore_case else 0
    try:
        compiled = re.compile(pattern, flags=flags)
    except re.error as exc:
        return [{"path": "<error>", "line": 0, "text": f"invalid regex: {exc}"}]

    root = Path(path).resolve()
    if not root.is_dir():
        return [{"path": str(root), "line": 0, "text": "path is not a directory"}]

    results: list[dict[str, str | int]] = []
    files_seen = 0

    for file_path in _iter_files(root, glob):
        files_seen += 1
        if files_seen > _DEFAULT_MAX_FILES:
            break
        if len(results) >= max_matches:
            break
        try:
            with file_path.open("r", encoding="utf-8", errors="strict") as f:
                for line_no, line in enumerate(f, start=1):
                    if compiled.search(line):
                        results.append(
                            {
                                "path": str(file_path.relative_to(root)),
                                "line": line_no,
                                "text": line.rstrip("\n"),
                            }
                        )
                        if len(results) >= max_matches:
                            break
        except (UnicodeDecodeError, OSError):
            # Binary file or unreadable — skip silently.
            continue

    return results


def _iter_files(root: Path, glob: str) -> Iterator[Path]:
    """Yield files under ``root`` matching ``glob``, skipping noise dirs."""
    # Path.rglob/glob doesn't natively skip our denylist, so walk manually.
    for candidate in root.glob(glob):
        if not candidate.is_file():
            continue
        # Skip if any path part is in the denylist.
        if any(part in _SKIP_DIRS for part in candidate.parts):
            continue
        yield candidate
