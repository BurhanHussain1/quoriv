"""Tests for `quoriv.core.agent`."""

from __future__ import annotations

from pathlib import Path

import pytest
from deepagents import FilesystemPermission

from quoriv.config import load_config
from quoriv.core.agent import PATH_PROTECTION, build_agent
from quoriv.models import MissingAPIKeyError

# ---------------------------------------------------------------------------
# PATH_PROTECTION rules
# ---------------------------------------------------------------------------


class TestPathProtection:
    def test_all_entries_are_filesystem_permissions(self) -> None:
        assert all(isinstance(rule, FilesystemPermission) for rule in PATH_PROTECTION)

    def test_all_entries_are_deny(self) -> None:
        assert all(rule.mode == "deny" for rule in PATH_PROTECTION)

    def test_protects_env_files(self) -> None:
        paths = {p for rule in PATH_PROTECTION for p in rule.paths}
        assert "/.env" in paths
        assert "/.env.*" in paths

    def test_protects_git_directory(self) -> None:
        paths = {p for rule in PATH_PROTECTION for p in rule.paths}
        assert "/.git/**" in paths

    def test_protects_ssh_for_read_and_write(self) -> None:
        ssh_rules = [r for r in PATH_PROTECTION if "/.ssh/**" in r.paths]
        assert ssh_rules, "expected at least one rule covering /.ssh/**"
        ops = {op for rule in ssh_rules for op in rule.operations}
        assert {"read", "write"}.issubset(ops)

    def test_protects_secrets_for_read_and_write(self) -> None:
        secrets_rules = [r for r in PATH_PROTECTION if "/secrets/**" in r.paths]
        assert secrets_rules, "expected at least one rule covering /secrets/**"
        ops = {op for rule in secrets_rules for op in rule.operations}
        assert {"read", "write"}.issubset(ops)


# ---------------------------------------------------------------------------
# build_agent
# ---------------------------------------------------------------------------


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
        # Override with a different OpenAI model — should still build.
        agent = build_agent(
            cfg,
            model_override="openai:gpt-4o-mini",
            cwd=tmp_path,
        )
        assert hasattr(agent, "astream_events")
