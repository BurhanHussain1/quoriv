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
- `src/quoriv/` folder skeleton with subpackages for `core`, `models`, `tools`, `permissions`, `plugins`, `plugins.mcp`, `ui`, `config`, `observability`, `repo`
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
- Tests for keychain (12), base (14), factory (7), openai (5) — **74 tests total**, all passing

#### Phase 0, Day 4 — CLI + chat loop (no DeepAgents yet)
- `quoriv.__main__` — makes `python -m quoriv` work the same as the `quoriv` console script
- `quoriv.cli` — Typer app with commands:
  - `quoriv chat [--model] [--mode]` — start an interactive session
  - `quoriv doctor` — health-check Rich table (Python, configured models, permission mode, API key status per provider)
  - `quoriv version` — print the installed version
  - `quoriv config show` — print the loaded merged configuration as JSON
  - `quoriv config set <provider>` — prompt for API key (hidden input) and store in OS keychain
  - `quoriv config list-providers` — table of known providers, env-var names, and whether a key is configured
- `quoriv.app` — async chat loop using `rich.Console` + `prompt_toolkit.PromptSession`; streams responses via LangChain `model.astream(messages)`; slash commands `/help`, `/clear`, `/exit`, `/quit`; graceful Ctrl+C handling; helpful prompt when an API key is missing
- Tests for the CLI commands using `typer.testing.CliRunner` (interactive `chat` deferred to Phase 1 integration tests)

#### Phase 0, Day 5 — DeepAgents wired
- `quoriv.core.agent.build_agent` — constructs a session-scoped `CompiledStateGraph` via `deepagents.create_deep_agent`, with `LocalShellBackend(root_dir=cwd)` for real file ops + shell, an in-memory `MemorySaver` checkpointer for multi-turn state, and always-on `PATH_PROTECTION` rules denying writes to `.env*`, `.git/**`, `.ssh/**`, and `secrets/**`
- `quoriv.core.PATH_PROTECTION` — tuple of `FilesystemPermission` deny rules that no permission mode can disable (security invariant)
- `quoriv.core.events` — Rich-rendering helpers for LangGraph events: `render_token`, `render_tool_start`, `render_tool_end`, `_format_args`
- `quoriv.app` rewritten to drive the DeepAgent:
  - Replaced direct `model.astream(messages)` with `agent.astream_events({"messages": [HumanMessage]}, version="v2")`
  - Per-session `thread_id` keys the checkpointer — `/clear` rotates to a new thread for a fresh conversation
  - Event-kind dispatch for `on_chat_model_stream`, `on_tool_start`, `on_tool_end`
- `quoriv chat` gains a `--cwd` option to target a specific repo root
- New tests:
  - `tests/unit/core/test_agent.py` — `PATH_PROTECTION` shape (5 rules covering env/git/ssh/secrets), `build_agent` raises `MissingAPIKeyError` without keys, returns a graph exposing `astream_events`/`ainvoke`/`invoke` when keys are present, honors `model_override`
  - `tests/unit/core/test_events.py` — `render_token`, `render_tool_start`, `render_tool_end` (short/long/None/multiline cases), `_format_args` (key=value, truncation per-value and per-call, non-dict fallback, empty dict)

With Day 5 wired, `quoriv chat` now has the full DeepAgents built-in toolset available out of the gate: `write_todos`, `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`, and `task` (for sub-agent delegation).

#### Phase 1 Slice 1 — Permission modes wired
- `quoriv.permissions.modes` — new module exporting `PermissionMode` (`Literal["read-only", "ask", "auto", "yolo"]`), `WRITE_TOOLS` (`{"write_file", "edit_file"}`), `SHELL_TOOLS` (`{"execute"}`), `interrupt_on_for_mode(mode)`, and `is_read_only(mode)`
- `quoriv.permissions.paths` — canonical home for `PATH_PROTECTION` (moved out of `core/agent.py`, where it was a transient placeholder)
- `quoriv.permissions.__init__` — re-exports the public surface from both submodules
- `quoriv.core.agent.build_agent` now accepts a `mode: PermissionMode = "ask"` parameter and applies the compiled `interrupt_on=` dict via `interrupt_on_for_mode(mode)`. Modes compile as:
  - `yolo` → `{}` (no prompts)
  - `auto` → `{"execute": True}` (prompt only before shell)
  - `ask`, `read-only` → `{"write_file": True, "edit_file": True, "execute": True}` (prompt before every write or shell call). Hard write denial in `read-only` is enforced at the approval-prompt UI (Slice 2).
- `quoriv.app.run_chat` validates the mode string against `ALLOWED_MODES` and passes it through to `build_agent`
- 24 new tests:
  - `tests/unit/permissions/test_modes.py` — 16 tests covering all 4 modes, tool-set membership and disjointness, dict freshness, `is_read_only`
  - `tests/unit/permissions/test_paths.py` — 8 tests covering rule shape, env/git/ssh/secrets coverage, POSIX rooting, immutability
- `tests/unit/core/test_agent.py` updated: `TestPathProtection` removed (moved with the data to `test_paths.py`), `TestBuildAgentModes` added (parametrized build for all 4 modes)

### Changed
- `PATH_PROTECTION` is no longer re-exported from `quoriv.core` — import it from `quoriv.permissions` instead.

**Test count: 108 → 130** (+22). All ruff / ruff format / mypy strict / pytest gates green.

### Changed

#### Architecture revision (post-DeepAgents audit)
- Adopted DeepAgents-reuse model after a deep read of the installed `deepagents` 0.6.1 SDK
- Added [`docs/DEEPAGENTS_REFERENCE.md`](docs/DEEPAGENTS_REFERENCE.md) — internal working reference for every DeepAgents feature Quoriv builds on
- Rewrote [`PROJECT_PLAN.md`](PROJECT_PLAN.md): updated folder tree, architecture diagram, Phase 1 / Phase 2 scope, and the permission-mode → DeepAgents-config mapping
- Narrowed scope of `src/quoriv/core/__init__.py` (DeepAgents IS the runtime; we just wrap `create_deep_agent`)
- Narrowed scope of `src/quoriv/tools/__init__.py` (only Quoriv-specific tools — AST, git, tests, web — DeepAgents owns files/shell/grep/todo)
- Narrowed scope of `src/quoriv/permissions/__init__.py` (mode translation only; `FilesystemMiddleware` enforces)
- Narrowed scope of `src/quoriv/repo/__init__.py` (tree-sitter symbol layer powering AST tools)

### Removed

- `src/quoriv/memory/` subpackage — DeepAgents' `MemoryMiddleware` loads `PROJECT.md` / `~/.quoriv/memory.md` directly via the `memory=[...]` parameter. No custom loader needed.

### Coming next (Phase 1 — remaining slices)
- **Slice 2:** Approval prompt UI for `interrupt_on` pauses (arrow-key choice; auto-deny in `read-only`)
- **Slice 1b:** Custom `wrap_tool_call` middleware that enforces `PATH_PROTECTION` against the live agent (DeepAgents 0.6.1 doesn't allow `permissions=` alongside sandbox backends, so we need a custom guard layer)
- **Slice 3:** Replace plain-text streaming with a markdown-aware Rich `Live` renderer; add a diff renderer for `edit_file` calls
- **Slice 4:** Quoriv-specific tools as plain callables — tree-sitter `find_symbol` / `go_to_definition` / `find_references`
- **Slice 5:** Git tools — `git_status`, `git_diff`, `git_log`, `git_blame`
- **Slice 6:** Language-aware `run_tests` tool
- **Slice 7:** Swap in-memory `MemorySaver` for `SqliteSaver` so sessions survive across restarts
- **Slice 8:** `/cost`, `/save`, `/load`, `/resume`, `/tools`, `/memory`, `/mode` slash commands + persistent status line
- **Slice 9:** Local JSON trace log + integration tests

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
