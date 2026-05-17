"""Tests for ``quoriv.core.memory`` — Phase 2 Slice 1."""

from __future__ import annotations

from pathlib import Path

from quoriv.core.memory import (
    PROJECT_MEMORY_FILENAME,
    QUORIV_MEMORY_FILENAME,
    MemoryCandidate,
    memory_candidates,
    resolve_memory_files,
)

# ---------------------------------------------------------------------------
# memory_candidates — pure path resolution, doesn't touch disk
# ---------------------------------------------------------------------------


class TestMemoryCandidates:
    def test_returns_two_candidates_in_load_order(self, fake_home: Path, tmp_path: Path) -> None:
        # Order matters: global first, project second. DeepAgents
        # concatenates in that order, so the project file is appended
        # to (and therefore can refine) the global one.
        result = memory_candidates(tmp_path)
        assert len(result) == 2
        assert result[0].label == "global"
        assert result[1].label == "project"

    def test_global_candidate_uses_home_dot_quoriv(self, fake_home: Path, tmp_path: Path) -> None:
        result = memory_candidates(tmp_path)
        assert result[0].path == fake_home / ".quoriv" / QUORIV_MEMORY_FILENAME

    def test_project_candidate_uses_supplied_cwd(self, fake_home: Path, tmp_path: Path) -> None:
        result = memory_candidates(tmp_path)
        assert result[1].path == tmp_path / PROJECT_MEMORY_FILENAME

    def test_candidate_named_tuple_unpacks(self, fake_home: Path, tmp_path: Path) -> None:
        # The MemoryCandidate is a NamedTuple — confirm both
        # attribute access and positional unpacking work, since both
        # forms are used in the codebase.
        candidate = memory_candidates(tmp_path)[0]
        label, path = candidate
        assert label == candidate.label
        assert path == candidate.path
        assert isinstance(candidate, MemoryCandidate)

    def test_called_with_different_cwds_returns_different_project_paths(
        self, fake_home: Path, tmp_path: Path
    ) -> None:
        sub_a = tmp_path / "a"
        sub_b = tmp_path / "b"
        sub_a.mkdir()
        sub_b.mkdir()
        a_paths = memory_candidates(sub_a)
        b_paths = memory_candidates(sub_b)
        assert a_paths[1].path != b_paths[1].path


# ---------------------------------------------------------------------------
# resolve_memory_files — filters to existing files
# ---------------------------------------------------------------------------


class TestResolveMemoryFiles:
    def test_returns_empty_when_neither_file_exists(self, fake_home: Path, tmp_path: Path) -> None:
        # ``fake_home`` redirects ``Path.home()`` to a clean dir so
        # nothing from the developer's real home leaks in.
        assert resolve_memory_files(tmp_path) == []

    def test_returns_only_project_file_when_global_missing(
        self, fake_home: Path, tmp_path: Path
    ) -> None:
        project_md = tmp_path / PROJECT_MEMORY_FILENAME
        project_md.write_text("# project context\n", encoding="utf-8")
        assert resolve_memory_files(tmp_path) == [project_md]

    def test_returns_only_global_file_when_project_missing(
        self, fake_home: Path, tmp_path: Path
    ) -> None:
        global_md = fake_home / ".quoriv" / QUORIV_MEMORY_FILENAME
        global_md.parent.mkdir(parents=True)
        global_md.write_text("# user memory\n", encoding="utf-8")
        assert resolve_memory_files(tmp_path) == [global_md]

    def test_returns_both_in_load_order(self, fake_home: Path, tmp_path: Path) -> None:
        # Global must come first so the project file can refine it.
        global_md = fake_home / ".quoriv" / QUORIV_MEMORY_FILENAME
        global_md.parent.mkdir(parents=True)
        global_md.write_text("g\n", encoding="utf-8")
        project_md = tmp_path / PROJECT_MEMORY_FILENAME
        project_md.write_text("p\n", encoding="utf-8")
        assert resolve_memory_files(tmp_path) == [global_md, project_md]

    def test_directory_with_memory_name_is_not_treated_as_file(
        self, fake_home: Path, tmp_path: Path
    ) -> None:
        # If someone (rarely) makes a directory named PROJECT.md, the
        # ``is_file()`` guard must keep it out of the load list —
        # passing a directory path to DeepAgents would just confuse
        # MemoryMiddleware.
        (tmp_path / PROJECT_MEMORY_FILENAME).mkdir()
        assert resolve_memory_files(tmp_path) == []
