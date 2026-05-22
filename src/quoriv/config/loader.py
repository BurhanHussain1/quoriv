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


def save_default_model(model_id: str) -> Path:
    """Persist ``model_id`` as ``model.default`` in the global config.

    Writes ``~/.quoriv/config.toml`` so the next ``quoriv chat`` picks
    the chosen model without needing ``--model``. Existing keys in the
    file are preserved — only ``[model] default`` is updated. The
    directory is created if missing.

    Returns:
        The absolute path that was written.
    """
    path = global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_toml(path) if path.is_file() else {}
    model_section = dict(existing.get("model", {}))
    model_section["default"] = model_id
    existing["model"] = model_section
    path.write_text(_format_toml(existing), encoding="utf-8")
    return path


def _format_toml(data: dict[str, Any]) -> str:
    """Serialize a config dict to TOML.

    We avoid taking a dependency on ``tomli-w`` for one writeback path —
    the config is small and only ever has string / int / bool leaves
    inside top-level tables, so a hand-rolled emitter is fine and keeps
    the install footprint flat.
    """
    lines: list[str] = []
    # Stable order: tables alphabetical, scalars first inside each.
    scalars: dict[str, Any] = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables: dict[str, dict[str, Any]] = {k: v for k, v in data.items() if isinstance(v, dict)}
    for key, value in scalars.items():
        lines.append(f"{key} = {_format_toml_value(value)}")
    if scalars and tables:
        lines.append("")
    for table_name in sorted(tables):
        lines.append(f"[{table_name}]")
        for key, value in tables[table_name].items():
            lines.append(f"{key} = {_format_toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_toml_value(value: Any) -> str:
    """Render a single TOML scalar."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(v) for v in value) + "]"
    # Fallback — JSON-style repr for anything exotic.
    return repr(value)


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
