"""Tests for `quoriv.core.agent`.

Path-protection rule shape lives in
:mod:`tests.unit.permissions.test_paths` — those constants are now
canonically defined in :mod:`quoriv.permissions.paths`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quoriv.config import load_config
from quoriv.core.agent import build_agent
from quoriv.models import MissingAPIKeyError
from quoriv.permissions import PermissionMode


class TestBuildAgent:
    def test_raises_missing_api_key_when_no_key_anywhere(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
    ) -> None:
        cfg = load_config()
        with pytest.raises(MissingAPIKeyError):
            build_agent(cfg)

    def test_returns_graph_with_streaming_api(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cfg = load_config()
        agent = build_agent(cfg, cwd=tmp_path)
        # We can't safely invoke the agent (no real OpenAI key), but the
        # compiled graph should at least expose the streaming entry points.
        assert hasattr(agent, "astream_events")
        assert hasattr(agent, "ainvoke")
        assert hasattr(agent, "invoke")

    def test_model_override_is_honored(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cfg = load_config()
        agent = build_agent(
            cfg,
            model_override="openai:gpt-4o-mini",
            cwd=tmp_path,
        )
        assert hasattr(agent, "astream_events")


class TestBuildAgentModes:
    """Each permission mode should build a valid agent."""

    @pytest.mark.parametrize("mode", ["read-only", "ask", "auto", "yolo"])
    def test_each_mode_builds_cleanly(
        self,
        mode: PermissionMode,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cfg = load_config()
        agent = build_agent(cfg, cwd=tmp_path, mode=mode)
        assert hasattr(agent, "astream_events")


# ---------------------------------------------------------------------------
# Phase 2 Slice 1 — memory= wiring
# ---------------------------------------------------------------------------


class TestBuildAgentMemoryWiring:
    """``build_agent`` should pass existing memory files to DeepAgents.

    We monkeypatch ``create_deep_agent`` to capture the kwargs Quoriv
    hands it. This avoids depending on DeepAgents' internal middleware
    behavior while still exercising the real ``build_agent`` path.
    """

    def _stub_factory(self, monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]) -> None:
        def fake_create_deep_agent(**kwargs: object) -> object:
            captured.update(kwargs)
            # Return a sentinel — the test never invokes it.
            return object()

        monkeypatch.setattr(
            "quoriv.core.agent.create_deep_agent",
            fake_create_deep_agent,
        )

    def test_memory_arg_is_none_when_no_files_present(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        captured: dict[str, object] = {}
        self._stub_factory(monkeypatch, captured)
        cfg = load_config()
        build_agent(cfg, cwd=tmp_path)
        # DeepAgents documents ``memory=None`` as "don't add the
        # middleware". An empty list would still attach the middleware
        # with zero entries — wrong shape.
        assert captured.get("memory") is None

    def test_memory_arg_contains_project_md_when_present(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        (tmp_path / "PROJECT.md").write_text("# project\n", encoding="utf-8")
        captured: dict[str, object] = {}
        self._stub_factory(monkeypatch, captured)
        cfg = load_config()
        build_agent(cfg, cwd=tmp_path)
        memory = captured.get("memory")
        assert isinstance(memory, list)
        assert any("PROJECT.md" in entry for entry in memory)

    def test_memory_arg_contains_global_memory_md_when_present(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        global_md = fake_home / ".quoriv" / "memory.md"
        global_md.parent.mkdir(parents=True)
        global_md.write_text("# user\n", encoding="utf-8")
        captured: dict[str, object] = {}
        self._stub_factory(monkeypatch, captured)
        cfg = load_config()
        build_agent(cfg, cwd=tmp_path)
        memory = captured.get("memory")
        assert isinstance(memory, list)
        assert any("memory.md" in entry for entry in memory)

    def test_memory_arg_ordered_global_then_project(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Order is part of the contract — DeepAgents concatenates in
        # the list order, so global → project lets the project file
        # refine the global one.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        global_md = fake_home / ".quoriv" / "memory.md"
        global_md.parent.mkdir(parents=True)
        global_md.write_text("g\n", encoding="utf-8")
        (tmp_path / "PROJECT.md").write_text("p\n", encoding="utf-8")
        captured: dict[str, object] = {}
        self._stub_factory(monkeypatch, captured)
        cfg = load_config()
        build_agent(cfg, cwd=tmp_path)
        memory = captured.get("memory")
        assert isinstance(memory, list)
        assert len(memory) == 2
        # First entry must be the global file, second the project file.
        assert "memory.md" in memory[0]
        assert "PROJECT.md" in memory[1]
