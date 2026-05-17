"""Tests for ``quoriv.core.subagents`` — Phase 2 Slice 4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from quoriv.config import load_config
from quoriv.config.schema import QuorivConfig
from quoriv.core.agent import build_agent
from quoriv.core.subagents import _resolve_model_token, build_subagents

# ---------------------------------------------------------------------------
# _resolve_model_token — pure
# ---------------------------------------------------------------------------


class TestResolveModelToken:
    def test_default_returns_model_default(self) -> None:
        config = QuorivConfig.model_validate({})
        assert _resolve_model_token("default", config) == config.model.default

    def test_fast_returns_model_fast(self) -> None:
        config = QuorivConfig.model_validate({})
        assert _resolve_model_token("fast", config) == config.model.fast

    def test_strong_returns_model_strong(self) -> None:
        config = QuorivConfig.model_validate({})
        assert _resolve_model_token("strong", config) == config.model.strong

    def test_literal_provider_name_returned_unchanged(self) -> None:
        config = QuorivConfig.model_validate({})
        assert _resolve_model_token("anthropic:claude-sonnet-4", config) == (
            "anthropic:claude-sonnet-4"
        )

    def test_uses_overridden_model_section(self) -> None:
        # When the user has redirected ``[model]``, the routing tokens
        # must follow — otherwise `quoriv chat --model X` and the
        # subagents disagree on which model they're talking to.
        config = QuorivConfig.model_validate(
            {
                "model": {
                    "default": "anthropic:claude-opus-4",
                    "fast": "openai:gpt-4o-mini",
                    "strong": "anthropic:claude-sonnet-4",
                }
            }
        )
        assert _resolve_model_token("default", config) == "anthropic:claude-opus-4"
        assert _resolve_model_token("fast", config) == "openai:gpt-4o-mini"
        assert _resolve_model_token("strong", config) == "anthropic:claude-sonnet-4"


# ---------------------------------------------------------------------------
# build_subagents — happy path with keychain stubbed
# ---------------------------------------------------------------------------


class TestBuildSubagents:
    """``build_subagents`` resolves and builds an LLM per role.

    The fake_keyring fixture in conftest stubs the keychain so a
    test env var (``OPENAI_API_KEY``) suffices for every model
    instance the factory hands back.
    """

    def test_returns_three_roles_in_order(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = load_config()
        result = build_subagents(config)
        names = [s["name"] for s in result]
        # Order matters: ``task`` lists them in this order in its
        # description, so users see researcher first when DeepAgents
        # renders the menu.
        assert names == ["researcher", "debugger", "reviewer"]

    def test_each_role_has_required_keys(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = load_config()
        for sub in build_subagents(config):
            assert sub["name"]
            assert sub["description"]
            assert sub["system_prompt"]
            assert sub["model"] is not None

    def test_researcher_uses_fast_model_by_default(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Capture model ids by monkeypatching the factory.
        captured: list[str] = []

        def fake_get_model(model_id: str) -> object:
            captured.append(model_id)
            return object()

        monkeypatch.setattr("quoriv.core.subagents.get_model", fake_get_model)
        config = QuorivConfig.model_validate({})
        build_subagents(config)
        # researcher is first (model.fast), debugger and reviewer
        # follow with model.strong.
        assert captured == [config.model.fast, config.model.strong, config.model.strong]

    def test_user_can_redirect_role_to_literal_model(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: list[str] = []
        monkeypatch.setattr(
            "quoriv.core.subagents.get_model",
            lambda mid: captured.append(mid) or object(),
        )
        config = QuorivConfig.model_validate(
            {"subagents": {"debugger": {"model": "anthropic:claude-opus-4"}}}
        )
        build_subagents(config)
        # researcher → fast (unchanged), debugger → literal override,
        # reviewer → strong (unchanged).
        assert captured == [
            config.model.fast,
            "anthropic:claude-opus-4",
            config.model.strong,
        ]

    def test_user_can_redirect_role_to_default_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: list[str] = []
        monkeypatch.setattr(
            "quoriv.core.subagents.get_model",
            lambda mid: captured.append(mid) or object(),
        )
        config = QuorivConfig.model_validate({"subagents": {"researcher": {"model": "default"}}})
        build_subagents(config)
        # researcher promoted from fast to default.
        assert captured[0] == config.model.default

    def test_descriptions_route_user_intent(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The role descriptions are the only thing the main agent
        # sees when choosing which subagent to invoke. Smoke check
        # that each mentions its job.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = load_config()
        result = {s["name"]: s["description"] for s in build_subagents(config)}
        assert "research" in result["researcher"].lower()
        assert "debug" in result["debugger"].lower()
        assert "review" in result["reviewer"].lower()


# ---------------------------------------------------------------------------
# Schema integration
# ---------------------------------------------------------------------------


class TestSubAgentsConfigSchema:
    def test_default_routing(self) -> None:
        config = QuorivConfig.model_validate({})
        assert config.subagents.researcher.model == "fast"
        assert config.subagents.debugger.model == "strong"
        assert config.subagents.reviewer.model == "strong"

    def test_partial_override_keeps_other_defaults(self) -> None:
        config = QuorivConfig.model_validate(
            {"subagents": {"researcher": {"model": "openai:gpt-4o"}}}
        )
        assert config.subagents.researcher.model == "openai:gpt-4o"
        # Untouched roles keep their built-in defaults.
        assert config.subagents.debugger.model == "strong"
        assert config.subagents.reviewer.model == "strong"

    def test_extra_role_rejected(self) -> None:
        # ``extra="forbid"`` keeps users from inventing role names —
        # the dispatch is hardcoded to researcher/debugger/reviewer
        # so an unknown key would be silently ignored without the
        # guard.
        with pytest.raises(ValidationError):
            QuorivConfig.model_validate({"subagents": {"linter": {"model": "fast"}}})

    def test_extra_field_within_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuorivConfig.model_validate(
                {"subagents": {"researcher": {"model": "fast", "tempo": "low"}}}
            )


# ---------------------------------------------------------------------------
# Integration with build_agent — subagents flow through to create_deep_agent
# ---------------------------------------------------------------------------


class TestBuildAgentSubagentsWiring:
    def test_subagents_kwarg_includes_three_built_ins(
        self,
        fake_home: Path,
        fake_keyring: dict[tuple[str, str], str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Reuse the create_deep_agent capture pattern from the memory
        # wiring test in test_agent.py.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        captured: dict[str, Any] = {}

        def fake_create_deep_agent(**kwargs: object) -> object:
            captured.update(kwargs)
            return object()

        monkeypatch.setattr("quoriv.core.agent.create_deep_agent", fake_create_deep_agent)

        config = load_config()
        build_agent(config, cwd=tmp_path)
        subagents = captured.get("subagents")
        assert isinstance(subagents, list)
        names = [s["name"] for s in subagents]
        assert names == ["researcher", "debugger", "reviewer"]
