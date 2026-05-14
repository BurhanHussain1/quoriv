"""Configuration: schemas, loaders, and API key storage for Quoriv.

Two TOML configs are merged (project overrides global):

    Global    ~/.quoriv/config.toml
    Project   <cwd or ancestor>/.quoriv/config.toml

API keys live in the OS keychain via the `keyring` library (with
environment-variable fallback for CI / containers); they are never read
from the TOML files.
"""

from __future__ import annotations

from quoriv.config.keychain import (
    PROVIDER_ENV_VARS,
    SERVICE_NAME,
    delete_api_key,
    get_api_key,
    list_known_providers,
    set_api_key,
)
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
    "PROVIDER_ENV_VARS",
    "SERVICE_NAME",
    "ModelConfig",
    "PermissionMode",
    "PermissionsConfig",
    "QuorivConfig",
    "Theme",
    "ToolsConfig",
    "UIConfig",
    "delete_api_key",
    "get_api_key",
    "global_config_path",
    "list_known_providers",
    "load_config",
    "project_config_path",
    "set_api_key",
]
