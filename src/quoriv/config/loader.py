"""TOML configuration loader with global + project merge.

Search order (later entries override earlier ones):

    1. Built-in defaults from `QuorivConfig` schema.
    2. ``~/.quoriv/config.toml`` (global, per-user).
    3. ``<cwd or ancestor>/.quoriv/config.toml`` (per-project).

The project config is found by walking up the directory tree from the
caller's working directory until a ``.quoriv/`` directory is found, so
running Quoriv from any subdirectory of a project picks up the same
config.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from quoriv.config.schema import QuorivConfig

CONFIG_DIR_NAME = ".quoriv"
"""Directory name searched for under home and in the project tree."""

CONFIG_FILE_NAME = "config.toml"
"""Config file name expected inside the `.quoriv/` directory."""


def global_config_path() -> Path:
    """Return the path to the global config (``~/.quoriv/config.toml``).

    The path is computed fresh on each call so tests that monkeypatch
    ``Path.home`` see the expected directory.
    """
    return Path.home() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def project_config_path(start: Path) -> Path | None:
    """Find the nearest ``.quoriv/config.toml`` walking up from ``start``.

    Returns the absolute path if found, else None.
    """
    start = start.resolve()
    for parent in [start, *start.parents]:
        candidate = parent / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate
    return None


def load_config(cwd: Path | None = None) -> QuorivConfig:
    """Load Quoriv configuration, merging global and project files.

    Args:
        cwd: Starting directory for the project-config search.
            Defaults to ``Path.cwd()``.

    Returns:
        A fully validated :class:`QuorivConfig` with defaults applied for
        any unset fields.

    Raises:
        pydantic.ValidationError: If a config file contains unknown keys
            or invalid values.
        tomllib.TOMLDecodeError: If a config file is malformed TOML.
    """
    global_data = _read_toml(global_config_path())
    project_path = project_config_path(cwd or Path.cwd())
    project_data = _read_toml(project_path) if project_path is not None else {}
    merged = _deep_merge(global_data, project_data)
    return QuorivConfig.model_validate(merged)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file; return ``{}`` if the path doesn't exist."""
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dicts; ``override`` wins on conflicting keys."""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
