"""Git tools — read and write git operations exposed to the agent.

Phase 1 Slice 5 ships four read-only ``@tool`` callables:

    git_status   Branch, ahead/behind, and working-tree state.
    git_diff     Working-tree, staged, or revision-range unified diff.
    git_log      Commit history with sha / author / email / date / subject.
    git_blame    Per-line authorship for a file (or a range of lines).

Phase 1 Slice 5b adds three write callables, each named in
:data:`quoriv.permissions.GIT_WRITE_TOOLS` so the HITL approval UI
prompts before they run (in ``ask`` / ``read-only`` modes):

    git_add      Stage paths (or all changes) into the index.
    git_commit   Create a commit from the current index.
    git_stash    Push the working tree onto the stash stack.

All tools shell out to ``git`` via :mod:`subprocess` with ``shell=False``
and a list of args — there is no shell expansion of user-controlled
input. Each tool returns a ``dict[str, Any]``; failure paths set an
``"error"`` key with a short human-readable message.

The write tools do **not** pass ``--no-gpg-sign`` or ``--no-verify``: they
respect the user's local git config. Tests configure
``commit.gpgsign=false`` per fixture repo so signing-required hosts do
not block the suite.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


def _run_git(args: list[str], cwd: str) -> tuple[int, str, str]:
    """Run ``git <args>`` in ``cwd`` and return ``(returncode, stdout, stderr)``.

    Always invokes git as a list of args (``shell=False``) so no shell
    expansion of user-controlled input is possible. ``text=True`` with
    ``errors='replace'`` decodes output as UTF-8 and tolerates bad bytes
    instead of raising.

    Raises:
        FileNotFoundError: If the ``git`` executable is not on ``PATH``.
    """
    root = str(Path(cwd).expanduser().resolve())
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _git_unavailable_error(exc: FileNotFoundError) -> dict[str, Any]:
    """Uniform error shape for the missing-``git``-binary case."""
    return {"error": f"git executable not found on PATH ({exc})"}


def _git_failure_error(rc: int, out: str, err: str, command: str) -> dict[str, Any]:
    """Uniform error shape for non-zero git exit codes."""
    return {"error": err.strip() or out.strip() or f"{command} exited {rc}"}


def _parse_status_porcelain(line: str) -> dict[str, str] | None:
    """Parse one line of ``git status --porcelain=v1`` output."""
    if len(line) < 4 or line[2] != " ":
        return None
    index_status = line[0]
    worktree_status = line[1]
    path = line[3:]
    # Renames are reported as "R  old -> new"; keep both halves.
    if " -> " in path:
        old_path, new_path = path.split(" -> ", 1)
        return {
            "path": new_path,
            "old_path": old_path,
            "index": index_status,
            "worktree": worktree_status,
        }
    return {"path": path, "index": index_status, "worktree": worktree_status}


def _parse_branch_line(line: str) -> tuple[str | None, int, int]:
    """Parse the leading ``## branch...upstream [ahead N, behind M]`` line.

    Returns ``(branch_name, ahead, behind)``. ``branch_name`` is ``None``
    for a detached HEAD (``## HEAD (no branch)``).
    """
    body = line.removeprefix("## ")
    if body.startswith("HEAD (no branch)"):
        return None, 0, 0
    bracket = body.find(" [")
    tracking_part = body[:bracket] if bracket != -1 else body
    branch = tracking_part.split("...", 1)[0]
    ahead = 0
    behind = 0
    if bracket != -1:
        end = body.rfind("]")
        meta = body[bracket + 2 : end] if end > bracket else ""
        for token in meta.split(", "):
            if token.startswith("ahead "):
                ahead = int(token.removeprefix("ahead ").strip())
            elif token.startswith("behind "):
                behind = int(token.removeprefix("behind ").strip())
    return branch, ahead, behind


@tool
def git_status(cwd: str = ".") -> dict[str, Any]:
    """Show the working-tree status of the git repo at ``cwd``.

    Args:
        cwd: Path to (or inside) the repo. Defaults to the current
            working directory.

    Returns:
        On success::

            {
              "branch": str | None,    # None on detached HEAD
              "ahead": int,            # commits ahead of upstream
              "behind": int,           # commits behind upstream
              "is_clean": bool,        # True iff no staged/unstaged changes
              "files": [
                {
                  "path": str,
                  "index": str,        # one-char status (e.g. "M", "A", " ")
                  "worktree": str,
                  "old_path"?: str,    # set on renames
                },
                ...
              ],
            }

        On failure: ``{"error": "<message>"}``.
    """
    try:
        rc, out, err = _run_git(["status", "--porcelain=v1", "--branch"], cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    if rc != 0:
        return _git_failure_error(rc, out, err, "git status")

    branch: str | None = None
    ahead = 0
    behind = 0
    files: list[dict[str, str]] = []
    for line in out.splitlines():
        if line.startswith("## "):
            branch, ahead, behind = _parse_branch_line(line)
            continue
        record = _parse_status_porcelain(line)
        if record is not None:
            files.append(record)
    return {
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "is_clean": not files,
        "files": files,
    }


@tool
def git_diff(
    path: str | None = None,
    staged: bool = False,
    revision_range: str | None = None,
    cwd: str = ".",
) -> dict[str, Any]:
    """Return a unified diff of changes in the git repo at ``cwd``.

    Args:
        path: Optional file or directory to scope the diff to.
        staged: If True, diff staged changes vs HEAD (``git diff --cached``).
        revision_range: Optional revision range like ``"main..HEAD"`` or
            ``"abc1234"``. Can be combined with ``path`` but not with
            ``staged``.
        cwd: Path to (or inside) the repo.

    Returns:
        On success: ``{"diff": str, "is_empty": bool}``.
        On failure: ``{"error": "<message>"}``.
    """
    args: list[str] = ["diff"]
    if staged:
        args.append("--cached")
    if revision_range is not None:
        args.append(revision_range)
    if path is not None:
        args.extend(["--", path])
    try:
        rc, out, err = _run_git(args, cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    if rc != 0:
        return _git_failure_error(rc, out, err, "git diff")
    return {"diff": out, "is_empty": not out.strip()}


_LOG_FIELDS: tuple[str, ...] = ("sha", "short_sha", "author", "email", "date", "subject")
_LOG_FORMAT = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s"


@tool
def git_log(
    limit: int = 20,
    path: str | None = None,
    cwd: str = ".",
) -> dict[str, Any]:
    """Return recent commits from the git repo at ``cwd``.

    Args:
        limit: Maximum number of commits to return. Must be >= 1.
        path: Optional file or directory to scope the log to
            (``git log -- <path>``).
        cwd: Path to (or inside) the repo.

    Returns:
        On success::

            {
              "entries": [
                {"sha": str, "short_sha": str, "author": str,
                 "email": str, "date": str, "subject": str},
                ...
              ],
              "count": int,
            }

        On failure: ``{"error": "<message>"}``.
    """
    if limit < 1:
        return {"error": f"limit must be >= 1, got {limit}"}
    args = ["log", f"-n{limit}", f"--pretty=format:{_LOG_FORMAT}", "--date=iso"]
    if path is not None:
        args.extend(["--", path])
    try:
        rc, out, err = _run_git(args, cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    if rc != 0:
        return _git_failure_error(rc, out, err, "git log")

    entries: list[dict[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != len(_LOG_FIELDS):
            continue
        entries.append(dict(zip(_LOG_FIELDS, parts, strict=True)))
    return {"entries": entries, "count": len(entries)}


# Matches one line of ``git blame --date=iso <file>`` output. The author may
# contain spaces ("Test User"), so we rely on the ISO timestamp + line number
# anchors to disambiguate the boundary. Boundary commits are marked with a
# leading "^" prefix on the SHA.
_BLAME_RE = re.compile(
    r"^(?P<sha>\^?[0-9a-f]+)\s+"
    r"\((?P<author>.+?)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\s[+-]\d{4})\s+"
    r"(?P<lineno>\d+)\)\s?(?P<content>.*)$"
)


@tool
def git_blame(
    file: str,
    line_start: int | None = None,
    line_end: int | None = None,
    cwd: str = ".",
) -> dict[str, Any]:
    """Return per-line authorship for a file in the git repo at ``cwd``.

    Args:
        file: Path (relative to ``cwd`` or absolute) of the file to blame.
        line_start: Optional 1-based starting line (inclusive).
        line_end: Optional 1-based ending line (inclusive). If only
            ``line_start`` is given, blames a single line.
        cwd: Path to (or inside) the repo.

    Returns:
        On success::

            {
              "file": str,
              "entries": [
                {"sha": str, "author": str, "date": str,
                 "lineno": int, "content": str},
                ...
              ],
            }

        On failure: ``{"error": "<message>"}``.
    """
    args: list[str] = ["blame", "--date=iso"]
    if line_start is not None:
        end = line_end if line_end is not None else line_start
        args.extend(["-L", f"{line_start},{end}"])
    args.extend(["--", file])
    try:
        rc, out, err = _run_git(args, cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    if rc != 0:
        return _git_failure_error(rc, out, err, "git blame")

    entries: list[dict[str, Any]] = []
    for line in out.splitlines():
        match = _BLAME_RE.match(line)
        if match is None:
            continue
        entries.append(
            {
                "sha": match.group("sha"),
                "author": match.group("author").strip(),
                "date": match.group("date"),
                "lineno": int(match.group("lineno")),
                "content": match.group("content"),
            }
        )
    return {"file": file, "entries": entries}


# ---------------------------------------------------------------------------
# Write tools (Slice 5b) — gated by HITL via GIT_WRITE_TOOLS.
# ---------------------------------------------------------------------------


def _staged_files(cwd: str) -> list[str]:
    """Return the list of currently-staged paths (``git diff --cached --name-only``)."""
    try:
        rc, out, _err = _run_git(["diff", "--cached", "--name-only"], cwd)
    except FileNotFoundError:
        return []
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line]


@tool
def git_add(
    paths: list[str] | None = None,
    cwd: str = ".",
) -> dict[str, Any]:
    """Stage changes into the git index of the repo at ``cwd``.

    Args:
        paths: Specific paths (files or directories) to stage. If ``None``
            or empty, runs ``git add -A`` to stage every change in the
            working tree.
        cwd: Path to (or inside) the repo.

    Returns:
        On success: ``{"staged_files": list[str]}`` — every path currently
        in the index after the add (derived from
        ``git diff --cached --name-only``). May be empty if nothing was
        actually added.
        On failure: ``{"error": "<message>"}``.
    """
    args: list[str] = ["add"]
    if paths:
        args.append("--")
        args.extend(paths)
    else:
        args.append("-A")
    try:
        rc, out, err = _run_git(args, cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    if rc != 0:
        return _git_failure_error(rc, out, err, "git add")
    return {"staged_files": _staged_files(cwd)}


@tool
def git_commit(message: str, cwd: str = ".") -> dict[str, Any]:
    """Create a commit from the current index in the repo at ``cwd``.

    Respects the user's local git config — does **not** override GPG
    signing or pre-commit hooks. If signing is enabled and fails, the
    underlying ``git commit`` call exits non-zero and the failure is
    returned in ``"error"``.

    Args:
        message: Commit message. A single non-empty string; embedded
            newlines are passed through to ``git commit -m`` unchanged.
        cwd: Path to (or inside) the repo.

    Returns:
        On success::

            {
              "sha": str,         # 40-char commit SHA of the new commit
              "short_sha": str,   # git's short SHA (typically 7+ chars)
              "subject": str,     # first line of the commit message
              "branch": str | None,  # current branch, or None on detached HEAD
            }

        On failure (including the "nothing to commit" case):
            ``{"error": "<message>"}``.
    """
    if not message:
        return {"error": "git_commit: message must be non-empty"}
    try:
        rc, out, err = _run_git(["commit", "-m", message], cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    if rc != 0:
        return _git_failure_error(rc, out, err, "git commit")

    # Pull the freshly-created commit's metadata from git itself rather
    # than parsing ``git commit``'s human-readable output (which varies
    # by locale and git version).
    try:
        _rc_sha, sha_out, _err_sha = _run_git(["rev-parse", "HEAD"], cwd)
        _rc_short, short_out, _err_short = _run_git(["rev-parse", "--short", "HEAD"], cwd)
        _rc_subj, subj_out, _err_subj = _run_git(["log", "-1", "--pretty=%s", "HEAD"], cwd)
        _rc_br, br_out, _err_br = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    branch_name = br_out.strip()
    return {
        "sha": sha_out.strip(),
        "short_sha": short_out.strip(),
        "subject": subj_out.strip(),
        "branch": branch_name if branch_name and branch_name != "HEAD" else None,
    }


@tool
def git_stash(
    message: str | None = None,
    include_untracked: bool = False,
    cwd: str = ".",
) -> dict[str, Any]:
    """Push the working tree onto the stash stack in the repo at ``cwd``.

    Args:
        message: Optional stash message (``git stash push -m <message>``).
        include_untracked: If True, also stash untracked files (``-u``).
        cwd: Path to (or inside) the repo.

    Returns:
        On success::

            {
              "stashed": bool,        # False when there were no changes to stash
              "message": str | None,  # echoed back when provided
            }

        On failure: ``{"error": "<message>"}``.
    """
    args: list[str] = ["stash", "push"]
    if include_untracked:
        args.append("-u")
    if message:
        args.extend(["-m", message])
    try:
        rc, out, err = _run_git(args, cwd)
    except FileNotFoundError as exc:
        return _git_unavailable_error(exc)
    if rc != 0:
        return _git_failure_error(rc, out, err, "git stash")
    # git stash exits 0 even when there's nothing to save — detect that.
    stashed = "No local changes to save" not in out
    return {"stashed": stashed, "message": message}
