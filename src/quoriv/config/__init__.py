"""Configuration: schemas and loaders for Quoriv TOML config files.

Two configs are merged (project overrides global):

    Global    ~/.quoriv/config.toml
    Project   <cwd or ancestor>/.quoriv/config.toml

API keys live in the OS keychain via the `keyring` library and are never
read from these TOML files.
"""

from __future__ import annotations

from quoriv.config.loader import (
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,
    global_config_path,
    load_config,
    project_config_path,
)
from quoriv.config.schema import (
    ModelConfig,
    PermissionMode,
    PermissionsConfig,
    QuorivConfig,
    Theme,
    ToolsConfig,
    UIConfig,
)

__all__ = [
    "CONFIG_DIR_NAME",
    "CONFIG_FILE_NAME",
    "ModelConfig",
    "PermissionMode",
    "PermissionsConfig",
    "QuorivConfig",
    "Theme",
    "ToolsConfig",
    "UIConfig",
    "global_config_path",
    "load_config",
    "project_config_path",
]
