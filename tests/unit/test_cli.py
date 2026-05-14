"""Tests for the Typer CLI (`quoriv.cli`).

The interactive ``chat`` command is exercised by integration tests in
Phase 1 — unit-testing it requires mocking both prompt_toolkit and
LangChain streaming, which adds little value at this layer.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from quoriv import __version__
from quoriv.cli import app
from quoriv.config.keychain import set_api_key


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_prints_version(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


class TestDoctor:
    def test_reports_default_sections(
        self,
        runner: CliRunner,
        fake_home,
        fake_keyring,
    ) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        # The Rich table uses unicode box drawing; check the labels only.
        for label in (
            "Python",
            "Default model",
            "Fast model",
            "Strong model",
            "Permission mode",
            "openai key",
        ):
            assert label in result.stdout

    def test_marks_missing_key(
        self,
        runner: CliRunner,
        fake_home,
        fake_keyring,
    ) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        # No env var, no keyring entry — openai should be missing.
        assert "missing" in result.stdout


# ---------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------


class TestConfigShow:
    def test_prints_valid_json(self, runner: CliRunner, fake_home) -> None:
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        # Find and parse the JSON body — Rich's print_json wraps it but the
        # raw structure is recoverable.
        start = result.stdout.find("{")
        end = result.stdout.rfind("}")
        assert start != -1 and end != -1, f"No JSON body in output:\n{result.stdout}"
        data = json.loads(result.stdout[start : end + 1])
        assert data["model"]["default"] == "openai:gpt-4.1"
        assert data["permissions"]["mode"] == "ask"


# ---------------------------------------------------------------------------
# config list-providers
# ---------------------------------------------------------------------------


class TestConfigListProviders:
    def test_lists_openai(
        self,
        runner: CliRunner,
        fake_home,
        fake_keyring,
    ) -> None:
        result = runner.invoke(app, ["config", "list-providers"])
        assert result.exit_code == 0
        assert "openai" in result.stdout
        assert "OPENAI_API_KEY" in result.stdout

    def test_marks_configured_after_set(
        self,
        runner: CliRunner,
        fake_home,
        fake_keyring,
    ) -> None:
        set_api_key("openai", "sk-test")
        result = runner.invoke(app, ["config", "list-providers"])
        assert result.exit_code == 0
        # "yes" should appear in the openai row.
        assert "yes" in result.stdout


# ---------------------------------------------------------------------------
# config set
# ---------------------------------------------------------------------------


class TestConfigSet:
    def test_stores_key_via_keychain(
        self,
        runner: CliRunner,
        fake_keyring: dict[tuple[str, str], str],
    ) -> None:
        result = runner.invoke(app, ["config", "set", "openai"], input="sk-test-12345\n")
        assert result.exit_code == 0, result.stdout
        assert "Saved" in result.stdout
        # The fake_keyring fixture exposes the backing store directly.
        assert fake_keyring[("quoriv", "openai")] == "sk-test-12345"

    def test_rejects_empty_key(
        self,
        runner: CliRunner,
        fake_keyring: dict[tuple[str, str], str],
    ) -> None:
        # Typer/Click's prompt re-prompts on empty input and ultimately aborts
        # with a non-zero exit. The keyring must not be touched.
        result = runner.invoke(app, ["config", "set", "openai"], input="\n")
        assert result.exit_code != 0
        assert fake_keyring == {}

    def test_rejects_unknown_provider(
        self,
        runner: CliRunner,
        fake_keyring,
    ) -> None:
        result = runner.invoke(app, ["config", "set", "notreal"], input="anything\n")
        assert result.exit_code == 1
        assert "Unknown provider" in result.stdout


# ---------------------------------------------------------------------------
# Top-level help / dispatch
# ---------------------------------------------------------------------------


class TestTopLevel:
    def test_help_lists_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("chat", "doctor", "config", "version"):
            assert cmd in result.stdout

    def test_no_args_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, [])
        # Typer exits 2 when no_args_is_help is set and no command given.
        assert result.exit_code == 2
        assert "Usage" in result.stdout or "Usage" in (result.stderr or "")
