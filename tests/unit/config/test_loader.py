"""Tests for `quoriv.config.loader`."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from quoriv.config.loader import (
    _deep_merge,
    global_config_path,
    load_config,
    project_config_path,
)

GLOBAL_TOML = dedent(
    """
    [model]
    default = "openai:gpt-4o-mini"

    [permissions]
    mode = "auto"
    """
).strip()

PROJECT_TOML = dedent(
    """
    [model]
    default = "anthropic:claude-sonnet-4-6"
    """
).strip()


# ---------------------------------------------------------------------------
# global_config_path
# ---------------------------------------------------------------------------


class TestGlobalConfigPath:
    def test_uses_path_home(self, fake_home: Path) -> None:
        assert global_config_path() == fake_home / ".quoriv" / "config.toml"


# ---------------------------------------------------------------------------
# project_config_path
# ---------------------------------------------------------------------------


class TestProjectConfigPath:
    def test_finds_config_in_starting_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".quoriv").mkdir()
        cfg = tmp_path / ".quoriv" / "config.toml"
        cfg.write_text(PROJECT_TOML)
        assert project_config_path(tmp_path) == cfg

    def test_walks_up_to_find_config(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        (project / ".quoriv").mkdir(parents=True)
        cfg = project / ".quoriv" / "config.toml"
        cfg.write_text(PROJECT_TOML)

        deep = project / "nested" / "deep" / "subdir"
        deep.mkdir(parents=True)
        assert project_config_path(deep) == cfg

    def test_returns_none_when_no_config_anywhere(self, tmp_path: Path) -> None:
        assert project_config_path(tmp_path) is None


# ---------------------------------------------------------------------------
# load_config: integration
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_defaults_when_no_files(self, fake_home: Path, tmp_path: Path) -> None:
        project = tmp_path / "project"
        project.mkdir()
        config = load_config(project)
        assert config.model.default == "openai:gpt-4.1"
        assert config.permissions.mode == "ask"
        assert config.ui.theme == "dark"

    def test_global_only(self, fake_home: Path, tmp_path: Path) -> None:
        (fake_home / ".quoriv").mkdir()
        (fake_home / ".quoriv" / "config.toml").write_text(GLOBAL_TOML)

        project = tmp_path / "project"
        project.mkdir()

        config = load_config(project)
        assert config.model.default == "openai:gpt-4o-mini"
        assert config.permissions.mode == "auto"
        # ui.theme still default
        assert config.ui.theme == "dark"

    def test_project_only(self, fake_home: Path, tmp_path: Path) -> None:
        project = tmp_path / "project"
        (project / ".quoriv").mkdir(parents=True)
        (project / ".quoriv" / "config.toml").write_text(PROJECT_TOML)

        config = load_config(project)
        assert config.model.default == "anthropic:claude-sonnet-4-6"
        # permissions.mode still default
        assert config.permissions.mode == "ask"

    def test_project_overrides_global(self, fake_home: Path, tmp_path: Path) -> None:
        (fake_home / ".quoriv").mkdir()
        (fake_home / ".quoriv" / "config.toml").write_text(GLOBAL_TOML)

        project = tmp_path / "project"
        (project / ".quoriv").mkdir(parents=True)
        (project / ".quoriv" / "config.toml").write_text(PROJECT_TOML)

        config = load_config(project)
        assert config.model.default == "anthropic:claude-sonnet-4-6"
        assert config.permissions.mode == "auto"  # from global, not overridden

    def test_project_config_found_walking_up(self, fake_home: Path, tmp_path: Path) -> None:
        project = tmp_path / "project"
        (project / ".quoriv").mkdir(parents=True)
        (project / ".quoriv" / "config.toml").write_text(PROJECT_TOML)

        deep = project / "src" / "module"
        deep.mkdir(parents=True)

        config = load_config(deep)
        assert config.model.default == "anthropic:claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# _deep_merge unit tests
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_simple_scalar_override(self) -> None:
        assert _deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_keys_only_in_base_kept(self) -> None:
        assert _deep_merge({"a": 1, "b": 2}, {"a": 9}) == {"a": 9, "b": 2}

    def test_keys_only_in_override_added(self) -> None:
        assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_nested_dict_merged_not_replaced(self) -> None:
        assert _deep_merge(
            {"model": {"default": "x", "fast": "y"}},
            {"model": {"default": "z"}},
        ) == {"model": {"default": "z", "fast": "y"}}

    def test_list_value_replaced_not_extended(self) -> None:
        # Override semantics for lists: replace, not append.
        assert _deep_merge({"tools": {"disabled": ["a", "b"]}}, {"tools": {"disabled": ["c"]}}) == {
            "tools": {"disabled": ["c"]}
        }

    def test_empty_inputs(self) -> None:
        assert _deep_merge({}, {}) == {}
        assert _deep_merge({"a": 1}, {}) == {"a": 1}
        assert _deep_merge({}, {"a": 1}) == {"a": 1}
