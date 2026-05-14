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

#### Phase 1 Slice 2 — Approval prompt UI for HITL pauses
- `quoriv.ui.prompts` — new module with `prompt_approval()`, `ApprovalDecision` (frozen dataclass), `parse_choice()`, `READ_ONLY_DENIAL_MESSAGE` constant, `DecisionType` Literal
- Renders a yellow Rich `Panel` showing tool name, JSON-formatted args, and middleware description; prompts via `prompt_toolkit` for `a/r` (aliases: `approve/reject/y/yes/n/no/deny`)
- `auto_deny=True` (used in `read-only` mode) renders the panel then auto-rejects with an explanatory message back to the agent
- `quoriv.app._stream_agent` refactored to `_drive_turn`: loop that streams events, calls `agent.aget_state()` to detect pending HITL interrupts, prompts the user for each `ActionRequest`, and resumes with `Command(resume={"decisions": [...]})`
- 28 new tests for `parse_choice` (approve/reject aliases, invalid input), `ApprovalDecision` (defaults, frozen behavior), `prompt_approval` (auto_deny path), `_render_approval_panel`, `_format_args`

**Test count: 130 → 158** (+28). All gates green.

#### Phase 1 Slice 3 — Markdown streaming + edit_file diff renderer
- `quoriv.ui.stream` — new module with `StreamRenderer`: Rich `Live` + `Markdown` wrapper that accumulates streamed tokens and live-renders them with markdown semantics (bold, code blocks, lists, syntax highlighting). Properties: `is_streaming`, `buffer`. Methods: `push(text)`, `finalize() -> str`. Safe to call `finalize` on idle state.
- `quoriv.ui.diff` — new module with `compute_diff()` (pure function returning `difflib.unified_diff` text) and `render_edit_diff()` (renders the diff with Rich `Syntax(theme="ansi_dark")` and an `edit_file` header line). Handles no-changes and missing-file-path cases.
- `quoriv.app._stream_events` rewritten:
  - Each call now owns a `StreamRenderer` instance (lifecycle managed by `try/finally`)
  - `on_chat_model_stream` → `renderer.push(text)` (replaces raw `render_token`)
  - `on_chat_model_end` and `on_tool_start` → `renderer.finalize()` to close the Live cleanly
  - `on_tool_start` for `edit_file` → `render_edit_diff()` (colored unified diff) instead of generic header
  - All other tools fall through to the existing `render_tool_start` / `render_tool_end`
- 16 new tests: `test_stream.py` (initial state, empty-push noop, accumulation, finalize semantics, restart after finalize); `test_diff.py` (identical strings → empty diff, change → unified diff, file path in headers, context lines respected, addition/removal only, render handles no-changes and missing path)

**Test count: 158 → 174** (+16). All gates green. Source files: 25 → 27.

#### Phase 1 Slice 1b — `PathProtectionMiddleware` (custom guard)
- `quoriv.permissions.guard` — new module with `PathProtectionMiddleware`, a `langchain.agents.middleware.AgentMiddleware` subclass that enforces `PATH_PROTECTION` deny rules at the middleware layer. Runs in `after_model` (and `aafter_model`), scans the latest `AIMessage.tool_calls` for path-bearing tools, and replaces denied calls with synthetic error `ToolMessage` objects so the agent observes the rejection on its next turn — a hard denial that bypasses HITL.
- `_TOOL_OPERATION` map covers DeepAgents' built-in filesystem tools (`ls`, `read_file`, `glob`, `grep` → `read`; `write_file`, `edit_file` → `write`). Tools outside the map are treated as path-irrelevant and pass through.
- `_check_denial` uses `wcmatch.glob.globmatch` with `BRACE | GLOBSTAR` flags — same semantics as DeepAgents' own `FilesystemMiddleware`, so deny patterns match identically whether DeepAgents adopts native sandbox-compatible `permissions=` later or not.
- `_extract_path` reads `file_path` or `path` from the tool call's args dict (the two argument names DeepAgents' file tools use).
- `quoriv.permissions.__init__` re-exports `PathProtectionMiddleware` from `guard`.
- `quoriv.core.agent.build_agent` now wires `middleware=[PathProtectionMiddleware(list(PATH_PROTECTION))]` into `create_deep_agent`. The custom guard layer is required because DeepAgents 0.6.1 raises `NotImplementedError` when `permissions=` is combined with a `SandboxBackendProtocol` backend (which `LocalShellBackend` is) — and we need `LocalShellBackend` for real shell execution.
- 26 new tests in `tests/unit/permissions/test_guard.py` covering: rule passthrough, allow-rule precedence, every denied tool name (write/edit/read/ls/glob/grep), path arg variants (`file_path` vs `path`), glob patterns (`*.env`, `.git/**`, `secrets/**`), unrelated tools passing through, no-AIMessage / no-tool-calls early exits, multiple tool calls in one message (some denied, some kept), `aafter_model` delegating to sync, immutable rules view, and integration with `PATH_PROTECTION` itself.

**Test count: 174 → 200** (+26). All gates green.

#### Phase 1 Slice 4 (minimal) — Python `find_symbol` tool
- `quoriv.tools.ast_tools` — new module with `find_symbol`, a `@tool`-decorated callable that walks `*.py` files under a path and returns every definition matching a target name. Returns a list of records: `{file, lineno, col_offset, kind, name, parent}`.
- Symbol kinds: `function`, `async_function`, `class`, `variable` (module/class-level `Name = ...` assignments). Methods recurse one level into class bodies and report `parent=<ClassName>`.
- Implementation uses the stdlib `ast` module only — no tree-sitter yet. Skips `.venv`, `venv`, `__pycache__`, `.git`, `build`, `dist` directories so third-party code doesn't pollute results. Silently skips files that fail to parse or decode.
- Accepts either a directory or a single file path. Nonexistent paths return `[]`.
- `quoriv.tools.__init__` — `QUORIV_TOOLS = [find_symbol]`; `quoriv.core.agent` registers it via `tools=list(QUORIV_TOOLS)` in `create_deep_agent`. The DeepAgents built-ins (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`, `task`, `write_todos`) remain — `find_symbol` is purely additive.
- 12 new tests in `tests/unit/tools/test_ast_tools.py` covering: function / async function / class / method-with-parent / module-level variable / no-match / subdirectory recursion / `.venv` + `__pycache__` skip / syntactically broken file skip / nonexistent path / single-file path / BaseTool registration.

Slice 4b (tree-sitter expansion for ~30 languages, `go_to_definition`, `find_references`) is deferred.

**Test count: 200 → 212** (+12). All gates green.

#### Phase 1 Slice 5 — Git tools (read-only)
- `quoriv.tools.git` — new module with four plain `@tool` callables shelling out to `git` via `subprocess.run` (`shell=False`, list args, `cwd`-bound, UTF-8 decoded with `errors="replace"`):
  - `git_status(cwd=".")` — returns `{branch, ahead, behind, is_clean, files}` (each file: `{path, index, worktree, old_path?}`). Detached HEAD reports `branch=None`. Renames keep `old_path`.
  - `git_diff(path=None, staged=False, revision_range=None, cwd=".")` — returns `{diff, is_empty}`. Combines path scoping with working-tree, staged (`--cached`), or revision-range diffs.
  - `git_log(limit=20, path=None, cwd=".")` — returns `{entries, count}` where each entry is `{sha, short_sha, author, email, date, subject}`. Uses `\x1f` field separator + ISO dates for unambiguous parsing.
  - `git_blame(file, line_start=None, line_end=None, cwd=".")` — returns `{file, entries}` with `{sha, author, date, lineno, content}` per line. `-L start,end` (or single line) scopes the blame.
- Uniform failure shape across all four tools: `{"error": "<message>"}` for non-zero git exit, not-a-repo errors, missing-file errors, invalid args (e.g., `limit < 1`), and the `git`-not-on-PATH case (`FileNotFoundError` → `"git executable not found on PATH (...)"`).
- Parser helpers `_parse_status_porcelain` and `_parse_branch_line` are exported for direct unit tests. Branch line covers `## main`, `## main...origin/main`, `[ahead N]`, `[behind M]`, `[ahead N, behind M]`, and `## HEAD (no branch)`.
- Write operations (`git add` / `git commit` / `git stash` / ...) are intentionally **not** in this slice — they land later behind `interrupt_on=` so HITL prompts before mutating the working tree.
- `quoriv.tools.__init__` — `QUORIV_TOOLS` now exposes `[find_symbol, git_status, git_diff, git_log, git_blame]`; `__all__` re-exports each tool by name.
- 42 new tests in `tests/unit/tools/test_git.py`:
  - `TestParseBranchLine` (6) — every branch-line variant
  - `TestParseStatusPorcelain` (6) — modified / staged / untracked / rename / too-short / malformed
  - `TestGitStatus` (6) — clean repo, untracked file, modified-then-staged, not-a-repo, `FileNotFoundError` for missing git binary, default-`cwd` via `monkeypatch.chdir`
  - `TestGitDiff` (7) — no-changes, working-tree, staged, revision range, path scoping, not-a-repo, bad revision
  - `TestGitLog` (7) — reverse-chronological ordering, entry-field shape, limit, path filter, invalid `limit`, empty repo, not-a-repo
  - `TestGitBlame` (5) — full-file, line range, single line, missing file, not-a-repo
  - `TestToolRegistration` (5) — each tool is a `BaseTool` with the right `.name` and is present in `QUORIV_TOOLS`
- Test infrastructure: a small in-file helper trio (`_git`, `_init_repo`, `_commit`) builds deterministic repos by pinning `GIT_AUTHOR_*` / `GIT_COMMITTER_*` env vars and `commit.gpgsign=false` per repo so tests are stable across hosts.

**Test count: 212 → 254** (+42). All gates green.

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
- **Slice 4b:** Tree-sitter expansion — multi-language parser registry, symbol index, `go_to_definition`, `find_references` for ~30 languages
- **Slice 5b:** Git **write** ops — `git_add`, `git_commit`, `git_stash` behind `interrupt_on=` (deferred from Slice 5)
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
