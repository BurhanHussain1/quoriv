# Changelog

All notable changes to Quoriv will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Initial repository scaffold (Phase 0, Day 1)
- `pyproject.toml` with full Phase 1 dependencies and optional groups for `ast`, `mcp`, `anthropic`, `gemini`, `ollama`, `dev`, `docs`
- Apache 2.0 license
- README with project overview, architecture, and usage examples
- `CONTRIBUTING.md` with development workflow and architectural rules
- `SECURITY.md` with disclosure policy
- `.gitignore` covering Python, IDE, and Quoriv-specific artifacts
- `.pre-commit-config.yaml` with ruff, mypy, and standard hooks
- GitHub Actions CI: `test.yml` (Windows / macOS / Linux × Python 3.11 / 3.12), `lint.yml` (ruff + mypy)

### Coming next (Phase 0, Day 2+)
- Pydantic v2 config schema and TOML loader (global + project)
- Source folder skeleton (`src/quoriv/` with all subpackage stubs)
- `keyring` integration for API keys
- Model factory with OpenAI provider
- Minimal Typer + Rich CLI streaming a response end-to-end
- DeepAgents wiring with a single `read_file` tool

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
