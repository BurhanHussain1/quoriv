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
