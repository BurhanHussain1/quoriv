# Changelog

All notable changes to Quoriv will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

#### Phase 0, Day 1 — Foundation scaffold
- `pyproject.toml` with full Phase 1 dependencies and optional groups (`ast`, `mcp`, `anthropic`, `gemini`, `ollama`, `dev`, `docs`)
- Apache 2.0 license
- README with project overview, architecture, and usage examples
- `CONTRIBUTING.md` with development workflow and architectural rules
- `SECURITY.md` with disclosure policy
- `.gitignore` covering Python, IDE, and Quoriv-specific artifacts
- `.pre-commit-config.yaml` with ruff, mypy, and standard hooks
- GitHub Actions CI: `test.yml` (Windows / macOS / Linux × Python 3.11 / 3.12), `lint.yml` (ruff + mypy)
- Issue templates: bug report, feature request

#### Phase 0, Day 2 — Config layer + folder skeleton
- `src/quoriv/` folder skeleton (12 subpackages with docstrings: `core`, `models`, `tools`, `permissions`, `memory`, `plugins`, `plugins.mcp`, `ui`, `config`, `observability`, `repo`)
- `src/quoriv/py.typed` (PEP 561 marker — Quoriv ships types)
- `quoriv.config.schema` — Pydantic v2 models (`QuorivConfig`, `ModelConfig`, `PermissionsConfig`, `UIConfig`, `ToolsConfig`) with `extra="forbid"` strictness and Literal types for enums (`PermissionMode`, `Theme`)
- `quoriv.config.loader` — TOML loader with global (`~/.quoriv/config.toml`) + project (`.quoriv/config.toml` walked up from cwd) merge; `global_config_path`, `project_config_path`, `load_config`, `_deep_merge`
- `config.example.toml` — annotated example at repo root
- `tests/conftest.py` with `fake_home` fixture
- 36 unit tests for config schema + loader

#### Phase 0, Day 3 — API keys + model factory
- `quoriv.config.keychain` — `keyring`-backed API key storage with env-var fallback precedence (`PROVIDER_ENV_VARS`, `set_api_key`, `get_api_key`, `delete_api_key`, `list_known_providers`)
- `quoriv.models.base` — `ModelSpec` (parses `"provider:name"` with first-colon split for Ollama tags), `ModelCapabilities`, `MissingAPIKeyError`
- `quoriv.models.factory` — `get_model("provider:name")` with lazy provider loading via `importlib`; `UnknownProviderError`; `list_providers`
- `quoriv.models.openai` — OpenAI provider via `langchain-openai` resolving keys through keychain
- `fake_keyring` test fixture (in-memory keychain + env-var isolation)
- Tests for keychain (12), base (16), factory (5), openai (5)

### Coming next (Phase 0, Day 4+)
- Minimal `cli.py` (Typer) + `app.py` (Rich chat loop) streaming an OpenAI response end-to-end
- `quoriv config set/get/list` subcommands and `quoriv doctor` health check
- DeepAgents wiring with a single `read_file` tool (Day 5)

---

<!--
Template for future entries:

## [x.y.z] - YYYY-MM-DD

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

-->
