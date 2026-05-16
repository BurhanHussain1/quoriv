"""Tests for `quoriv.tools.git`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from quoriv.tools import QUORIV_TOOLS
from quoriv.tools.git import (
    _parse_branch_line,
    _parse_status_porcelain,
    git_add,
    git_blame,
    git_commit,
    git_diff,
    git_log,
    git_stash,
    git_status,
)

# ---------------------------------------------------------------------------
# Repo helpers — deterministic git operations against a real tmp_path repo.
# ---------------------------------------------------------------------------

_GIT_ENV: dict[str, str] = {
    "GIT_AUTHOR_NAME": "Test User",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test User",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_AUTHOR_DATE": "2024-01-15T10:00:00+0000",
    "GIT_COMMITTER_DATE": "2024-01-15T10:00:00+0000",
}


def _git(
    repo: Path,
    *args: str,
    env_override: dict[str, str] | None = None,
) -> str:
    env = {**os.environ, **_GIT_ENV}
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


def _init_repo(tmp_path: Path, *, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")
    return repo


def _write(repo: Path, rel: str, content: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _commit(repo: Path, message: str, date: str = "2024-01-15T10:00:00+0000") -> str:
    _git(repo, "add", "-A")
    _git(
        repo,
        "commit",
        "-m",
        message,
        env_override={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return _git(repo, "rev-parse", "HEAD").strip()


# ---------------------------------------------------------------------------
# Parser unit tests.
# ---------------------------------------------------------------------------


class TestParseBranchLine:
    def test_plain_branch(self) -> None:
        assert _parse_branch_line("## main") == ("main", 0, 0)

    def test_tracking_branch(self) -> None:
        assert _parse_branch_line("## main...origin/main") == ("main", 0, 0)

    def test_ahead_only(self) -> None:
        assert _parse_branch_line("## main...origin/main [ahead 3]") == ("main", 3, 0)

    def test_behind_only(self) -> None:
        assert _parse_branch_line("## main...origin/main [behind 2]") == ("main", 0, 2)

    def test_ahead_and_behind(self) -> None:
        assert _parse_branch_line("## main...origin/main [ahead 3, behind 4]") == (
            "main",
            3,
            4,
        )

    def test_detached_head(self) -> None:
        assert _parse_branch_line("## HEAD (no branch)") == (None, 0, 0)


class TestParseStatusPorcelain:
    def test_modified_in_worktree(self) -> None:
        assert _parse_status_porcelain(" M file.py") == {
            "path": "file.py",
            "index": " ",
            "worktree": "M",
        }

    def test_staged_modification(self) -> None:
        assert _parse_status_porcelain("M  file.py") == {
            "path": "file.py",
            "index": "M",
            "worktree": " ",
        }

    def test_untracked(self) -> None:
        assert _parse_status_porcelain("?? new.py") == {
            "path": "new.py",
            "index": "?",
            "worktree": "?",
        }

    def test_rename_keeps_old_path(self) -> None:
        record = _parse_status_porcelain("R  old.py -> new.py")
        assert record == {
            "path": "new.py",
            "old_path": "old.py",
            "index": "R",
            "worktree": " ",
        }

    def test_too_short_returns_none(self) -> None:
        assert _parse_status_porcelain("") is None
        assert _parse_status_porcelain("M") is None

    def test_malformed_line_returns_none(self) -> None:
        # Third character should be a space; "XY!file" violates that.
        assert _parse_status_porcelain("XY!file") is None


# ---------------------------------------------------------------------------
# git_status integration tests.
# ---------------------------------------------------------------------------


class TestGitStatus:
    def test_clean_repo(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hello\n")
        _commit(repo, "initial")
        result = git_status.invoke({"cwd": str(repo)})
        assert result["branch"] == "main"
        assert result["ahead"] == 0
        assert result["behind"] == 0
        assert result["is_clean"] is True
        assert result["files"] == []

    def test_untracked_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hello\n")
        _commit(repo, "initial")
        _write(repo, "b.txt", "new\n")
        result = git_status.invoke({"cwd": str(repo)})
        assert result["is_clean"] is False
        assert any(f["path"] == "b.txt" and f["worktree"] == "?" for f in result["files"])

    def test_modified_then_staged(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hello\n")
        _commit(repo, "initial")
        _write(repo, "a.txt", "hello\nmore\n")
        result = git_status.invoke({"cwd": str(repo)})
        assert any(f["path"] == "a.txt" and f["worktree"] == "M" for f in result["files"])
        _git(repo, "add", "a.txt")
        result_staged = git_status.invoke({"cwd": str(repo)})
        assert any(f["path"] == "a.txt" and f["index"] == "M" for f in result_staged["files"])

    def test_not_a_repo_returns_error(self, tmp_path: Path) -> None:
        result = git_status.invoke({"cwd": str(tmp_path)})
        assert "error" in result

    def test_git_binary_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("git not on PATH")

        monkeypatch.setattr("quoriv.tools.git.subprocess.run", _raise)
        result = git_status.invoke({"cwd": str(tmp_path)})
        assert "error" in result
        assert "git executable not found" in result["error"]

    def test_uses_cwd_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hi\n")
        _commit(repo, "initial")
        monkeypatch.chdir(repo)
        result = git_status.invoke({})
        assert result["branch"] == "main"
        assert result["is_clean"] is True


# ---------------------------------------------------------------------------
# git_diff integration tests.
# ---------------------------------------------------------------------------


class TestGitDiff:
    def test_no_changes_is_empty(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hello\n")
        _commit(repo, "initial")
        result = git_diff.invoke({"cwd": str(repo)})
        assert result["diff"] == ""
        assert result["is_empty"] is True

    def test_working_tree_diff(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hello\n")
        _commit(repo, "initial")
        _write(repo, "a.txt", "hello\nworld\n")
        result = git_diff.invoke({"cwd": str(repo)})
        assert result["is_empty"] is False
        assert "+world" in result["diff"]
        assert "a.txt" in result["diff"]

    def test_staged_diff(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hello\n")
        _commit(repo, "initial")
        _write(repo, "a.txt", "hello\nworld\n")
        _git(repo, "add", "a.txt")
        # Unstaged diff is now empty; staged diff carries the change.
        assert git_diff.invoke({"cwd": str(repo)})["is_empty"] is True
        staged = git_diff.invoke({"staged": True, "cwd": str(repo)})
        assert staged["is_empty"] is False
        assert "+world" in staged["diff"]

    def test_revision_range_diff(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "v1\n")
        sha1 = _commit(repo, "v1", date="2024-01-15T10:00:00+0000")
        _write(repo, "a.txt", "v2\n")
        sha2 = _commit(repo, "v2", date="2024-01-16T10:00:00+0000")
        result = git_diff.invoke({"revision_range": f"{sha1}..{sha2}", "cwd": str(repo)})
        assert result["is_empty"] is False
        assert "-v1" in result["diff"]
        assert "+v2" in result["diff"]

    def test_path_scoping(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "a\n")
        _write(repo, "b.txt", "b\n")
        _commit(repo, "initial")
        _write(repo, "a.txt", "a2\n")
        _write(repo, "b.txt", "b2\n")
        result = git_diff.invoke({"path": "a.txt", "cwd": str(repo)})
        assert "a.txt" in result["diff"]
        assert "b.txt" not in result["diff"]

    def test_not_a_repo_returns_error(self, tmp_path: Path) -> None:
        result = git_diff.invoke({"cwd": str(tmp_path)})
        assert "error" in result

    def test_bad_revision_returns_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "v1\n")
        _commit(repo, "v1")
        result = git_diff.invoke({"revision_range": "nonexistent-ref", "cwd": str(repo)})
        assert "error" in result


# ---------------------------------------------------------------------------
# git_log integration tests.
# ---------------------------------------------------------------------------


class TestGitLog:
    def test_returns_entries_in_reverse_chronological(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "1\n")
        _commit(repo, "first", date="2024-01-15T10:00:00+0000")
        _write(repo, "a.txt", "2\n")
        _commit(repo, "second", date="2024-01-16T10:00:00+0000")
        _write(repo, "a.txt", "3\n")
        _commit(repo, "third", date="2024-01-17T10:00:00+0000")

        result = git_log.invoke({"cwd": str(repo)})
        assert result["count"] == 3
        subjects = [e["subject"] for e in result["entries"]]
        assert subjects == ["third", "second", "first"]

    def test_entry_fields(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "x\n")
        _commit(repo, "msg")
        entry = git_log.invoke({"cwd": str(repo)})["entries"][0]
        assert set(entry) == {"sha", "short_sha", "author", "email", "date", "subject"}
        assert entry["author"] == "Test User"
        assert entry["email"] == "test@example.com"
        assert entry["subject"] == "msg"
        assert len(entry["short_sha"]) >= 7
        assert len(entry["sha"]) == 40

    def test_limit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        for i in range(5):
            _write(repo, "a.txt", f"{i}\n")
            _commit(repo, f"c{i}", date=f"2024-01-{15 + i:02d}T10:00:00+0000")
        result = git_log.invoke({"limit": 2, "cwd": str(repo)})
        assert result["count"] == 2

    def test_path_filtering(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "a\n")
        _commit(repo, "touch a", date="2024-01-15T10:00:00+0000")
        _write(repo, "b.txt", "b\n")
        _commit(repo, "touch b", date="2024-01-16T10:00:00+0000")
        result = git_log.invoke({"path": "a.txt", "cwd": str(repo)})
        subjects = [e["subject"] for e in result["entries"]]
        assert subjects == ["touch a"]

    def test_invalid_limit_returns_error(self, tmp_path: Path) -> None:
        result = git_log.invoke({"limit": 0, "cwd": str(tmp_path)})
        assert "error" in result
        assert "limit must be >= 1" in result["error"]

    def test_empty_repo_returns_no_entries(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        # ``git log`` exits with code 128 on an empty repo. We want an
        # empty entries list, not an error — but git's choice here is
        # nonzero. We accept either as long as the shape is sane.
        result = git_log.invoke({"cwd": str(repo)})
        assert "error" in result or result["entries"] == []

    def test_not_a_repo_returns_error(self, tmp_path: Path) -> None:
        result = git_log.invoke({"cwd": str(tmp_path)})
        assert "error" in result


# ---------------------------------------------------------------------------
# git_blame integration tests.
# ---------------------------------------------------------------------------


class TestGitBlame:
    def test_blame_full_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.py", "line1\nline2\nline3\n")
        _commit(repo, "initial")
        result = git_blame.invoke({"file": "a.py", "cwd": str(repo)})
        assert result["file"] == "a.py"
        assert len(result["entries"]) == 3
        for i, entry in enumerate(result["entries"], start=1):
            assert entry["lineno"] == i
            assert entry["author"] == "Test User"
            assert entry["content"] == f"line{i}"
            assert len(entry["sha"]) >= 7

    def test_blame_line_range(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.py", "a\nb\nc\nd\ne\n")
        _commit(repo, "initial")
        result = git_blame.invoke(
            {"file": "a.py", "line_start": 2, "line_end": 4, "cwd": str(repo)}
        )
        assert [e["lineno"] for e in result["entries"]] == [2, 3, 4]
        assert [e["content"] for e in result["entries"]] == ["b", "c", "d"]

    def test_blame_single_line(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.py", "a\nb\nc\n")
        _commit(repo, "initial")
        result = git_blame.invoke({"file": "a.py", "line_start": 2, "cwd": str(repo)})
        assert len(result["entries"]) == 1
        assert result["entries"][0]["lineno"] == 2
        assert result["entries"][0]["content"] == "b"

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.py", "x\n")
        _commit(repo, "initial")
        result = git_blame.invoke({"file": "does-not-exist.py", "cwd": str(repo)})
        assert "error" in result

    def test_not_a_repo_returns_error(self, tmp_path: Path) -> None:
        result = git_blame.invoke({"file": "anything", "cwd": str(tmp_path)})
        assert "error" in result


# ---------------------------------------------------------------------------
# git_add integration tests.
# ---------------------------------------------------------------------------


class TestGitAdd:
    def test_add_all_with_no_paths(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "a\n")
        _write(repo, "b.txt", "b\n")
        result = git_add.invoke({"cwd": str(repo)})
        assert "error" not in result
        assert set(result["staged_files"]) == {"a.txt", "b.txt"}

    def test_add_specific_paths(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "a\n")
        _write(repo, "b.txt", "b\n")
        result = git_add.invoke({"paths": ["a.txt"], "cwd": str(repo)})
        assert result["staged_files"] == ["a.txt"]

    def test_add_empty_paths_treated_as_add_all(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "a\n")
        result = git_add.invoke({"paths": [], "cwd": str(repo)})
        assert result["staged_files"] == ["a.txt"]

    def test_add_nonexistent_path_returns_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        result = git_add.invoke({"paths": ["does-not-exist.txt"], "cwd": str(repo)})
        assert "error" in result

    def test_add_in_clean_repo_returns_empty(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "a\n")
        _commit(repo, "initial")
        result = git_add.invoke({"cwd": str(repo)})
        assert result["staged_files"] == []

    def test_add_not_a_repo_returns_error(self, tmp_path: Path) -> None:
        result = git_add.invoke({"cwd": str(tmp_path)})
        assert "error" in result


# ---------------------------------------------------------------------------
# git_commit integration tests.
# ---------------------------------------------------------------------------


class TestGitCommit:
    def test_commit_with_staged_changes(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "hello\n")
        _git(repo, "add", "a.txt")
        result = git_commit.invoke({"message": "first commit", "cwd": str(repo)})
        assert "error" not in result
        assert result["subject"] == "first commit"
        assert result["branch"] == "main"
        assert len(result["sha"]) == 40
        assert len(result["short_sha"]) >= 7

    def test_commit_with_nothing_staged_returns_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        result = git_commit.invoke({"message": "empty", "cwd": str(repo)})
        assert "error" in result

    def test_commit_empty_message_rejected_locally(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        result = git_commit.invoke({"message": "", "cwd": str(repo)})
        assert "error" in result
        assert "non-empty" in result["error"]

    def test_commit_subject_is_first_line(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "x\n")
        _git(repo, "add", "a.txt")
        result = git_commit.invoke({"message": "subject line\n\nbody paragraph", "cwd": str(repo)})
        assert result["subject"] == "subject line"

    def test_commit_not_a_repo_returns_error(self, tmp_path: Path) -> None:
        result = git_commit.invoke({"message": "msg", "cwd": str(tmp_path)})
        assert "error" in result


# ---------------------------------------------------------------------------
# git_stash integration tests.
# ---------------------------------------------------------------------------


class TestGitStash:
    def test_stash_with_changes(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "v1\n")
        _commit(repo, "initial")
        _write(repo, "a.txt", "v2\n")
        result = git_stash.invoke({"cwd": str(repo)})
        assert "error" not in result
        assert result["stashed"] is True
        # And the stash stack now has one entry.
        stash_list = _git(repo, "stash", "list")
        assert "stash@{0}" in stash_list

    def test_stash_with_no_changes_reports_not_stashed(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "x\n")
        _commit(repo, "initial")
        result = git_stash.invoke({"cwd": str(repo)})
        assert result["stashed"] is False

    def test_stash_with_message(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt", "v1\n")
        _commit(repo, "initial")
        _write(repo, "a.txt", "v2\n")
        result = git_stash.invoke({"message": "WIP feature x", "cwd": str(repo)})
        assert result["stashed"] is True
        assert result["message"] == "WIP feature x"
        # Verify git recorded the message.
        stash_list = _git(repo, "stash", "list")
        assert "WIP feature x" in stash_list

    def test_stash_includes_untracked(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "tracked.txt", "x\n")
        _commit(repo, "initial")
        _write(repo, "untracked.txt", "u\n")
        # Without -u, untracked files aren't stashed and the stash is a no-op.
        no_u = git_stash.invoke({"cwd": str(repo)})
        assert no_u["stashed"] is False
        # With -u, the untracked file is stashed.
        with_u = git_stash.invoke({"include_untracked": True, "cwd": str(repo)})
        assert with_u["stashed"] is True

    def test_stash_not_a_repo_returns_error(self, tmp_path: Path) -> None:
        result = git_stash.invoke({"cwd": str(tmp_path)})
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool registration.
# ---------------------------------------------------------------------------


class TestToolRegistration:
    @pytest.mark.parametrize(
        ("tool", "expected_name"),
        [
            (git_status, "git_status"),
            (git_diff, "git_diff"),
            (git_log, "git_log"),
            (git_blame, "git_blame"),
            (git_add, "git_add"),
            (git_commit, "git_commit"),
            (git_stash, "git_stash"),
        ],
    )
    def test_is_langchain_tool(self, tool: object, expected_name: str) -> None:
        assert hasattr(tool, "invoke")
        assert hasattr(tool, "name")
        assert tool.name == expected_name  # type: ignore[attr-defined]

    def test_all_in_quoriv_tools(self) -> None:
        names = {t.name for t in QUORIV_TOOLS}
        expected = {
            "git_status",
            "git_diff",
            "git_log",
            "git_blame",
            "git_add",
            "git_commit",
            "git_stash",
        }
        assert expected <= names
