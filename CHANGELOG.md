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

#### Phase 1 Slice 7 — SQLite session persistence + `/save` / `/load` / `/resume`
- `langgraph-checkpoint-sqlite>=2.0.0` added to runtime dependencies (resolves to 3.1.0). `aiosqlite>=0.20.0` was already in place.
- `quoriv.core.persistence` — new module with:
  - Path helpers: `quoriv_dir(cwd)`, `db_path(cwd)`, `registry_path(cwd)`, `ensure_quoriv_dir(cwd)`. The agent's SQLite checkpointer lives at `<cwd>/.quoriv/sessions.db` and the named-session sidecar at `<cwd>/.quoriv/sessions.json` (per-project, mirroring how `.git/` is per-repo).
  - `NamedSession` frozen dataclass: `{name, thread_id, saved_at}` (ISO-8601 UTC timestamp).
  - `SessionRegistry` — file-backed `name → thread_id` mapping. Loaded on construction, written eagerly on every mutation. Malformed / missing files reset to an empty registry rather than raising — the underlying SQLite DB is the real source of truth, so a corrupted name index is a recoverable convenience-layer issue. Public API: `for_cwd(cwd)`, `save(name, thread_id, *, now=None)`, `load(name)`, `list_named()`, `most_recent()`, `remove(name)`, `path`.
- `quoriv.core.__init__` re-exports `SessionRegistry`, `NamedSession`, `db_path`, `ensure_quoriv_dir`, `quoriv_dir`, `registry_path`.
- `quoriv.app.run_chat` rewritten to manage the saver lifecycle:
  - Resolves `cwd` to an absolute `Path`, calls `ensure_quoriv_dir`, opens `AsyncSqliteSaver.from_conn_string(str(sessions_db))` via `async with`, passes the saver to `build_agent(..., checkpointer=saver)`. The prompt-loop body moved into `_interactive_loop(console, agent, registry, mode)` so the lifecycle stays explicit.
- New slash commands (with handler helpers `_handle_save`, `_handle_load`, `_handle_resume`, `_print_saved_sessions`):
  - `/save [name]` — anchor the current thread under `name` (default: first 8 chars of the thread id). Overwrites any prior entry under that name.
  - `/load` — list saved sessions (most-recent first), or `/load <name>` to switch the active thread.
  - `/resume` — switch to the most-recently-saved thread (by `saved_at`).
- `_handle_slash` signature now takes a `SessionRegistry`; legacy commands (`/help`, `/clear`, `/exit`, `/quit`) still work and surface the new entries through `/help`. `SLASH_COMMANDS` extended accordingly.
- 44 new tests:
  - `tests/unit/core/test_persistence.py` (26) — path helpers, construction (empty / no-file-on-init), `save` returns/persists/round-trips/overwrites/timestamps, `load` known/unknown, `list_named` ordering, `most_recent` by `saved_at`, `remove` existing/unknown/persists, malformed-file recovery (bad JSON, non-dict root, missing `sessions` key, non-list value, dropped-field entries).
  - `tests/unit/test_app_slash.py` (18) — `SLASH_COMMANDS` table, `/save` with-name / default-name / reports / empty-thread-id / overwrites, `/load` known / unknown / empty-list / populated-list, `/resume` most-recent / empty-registry, legacy `/exit` / `/quit` / `/clear` / `/help` / unknown-command paths.

**Test count: 254 → 298** (+44). All gates green.

#### Phase 1 Slice 5b — Git write tools (HITL-gated)
- `quoriv.tools.git` extended with three write callables sharing the same `subprocess.run` (`shell=False`, list args, `cwd`-bound) and `dict[str, Any]` return shape as the read tools:
  - `git_add(paths=None, cwd=".")` — stages specific paths or all changes (`git add -A`). Returns `{"staged_files": list[str]}` from `git diff --cached --name-only` after the add. Empty `paths` list is treated as "add all".
  - `git_commit(message, cwd=".")` — creates a commit from the current index. Returns `{"sha", "short_sha", "subject", "branch": str | None}` parsed from `git rev-parse` / `git log -1` rather than the locale-sensitive `git commit` output. Empty message rejected locally with a structured error.
  - `git_stash(message=None, include_untracked=False, cwd=".")` — pushes the working tree onto the stash. Returns `{"stashed": bool, "message": str | None}` — `stashed=False` when git printed `"No local changes to save"`.
- All three respect local git config: no `--no-gpg-sign`, no `--no-verify`. Tests configure `commit.gpgsign=false` per fixture repo so signing-required hosts do not block the suite.
- `quoriv.permissions.modes.GIT_WRITE_TOOLS = frozenset({"git_add", "git_commit", "git_stash"})` — Quoriv-specific git tools that mutate repo state, gated alongside `WRITE_TOOLS` in `ask` / `read-only` modes. `auto` mode lets them run silently (like `write_file`); `yolo` lets everything through.
- `interrupt_on_for_mode("ask")` and `interrupt_on_for_mode("read-only")` now include the new tool names; `auto` and `yolo` deliberately do not.
- `quoriv.permissions.__init__` re-exports `GIT_WRITE_TOOLS`. `quoriv.tools.__init__` extends `QUORIV_TOOLS` to include the three new tools and re-exports them.
- 23 new tests:
  - `tests/unit/permissions/test_modes.py` (5) — `GIT_WRITE_TOOLS` membership shape, pairwise-disjoint with `WRITE_TOOLS` and `SHELL_TOOLS`, `auto` does NOT gate them, `ask` does, `read-only` does.
  - `tests/unit/tools/test_git.py` (18): `TestGitAdd` (6) — add-all, specific paths, empty-paths defaults, nonexistent path errors, clean-repo returns empty, not-a-repo errors. `TestGitCommit` (5) — staged commit, nothing-staged errors, empty-message rejected locally, subject is first line, not-a-repo errors. `TestGitStash` (5) — with changes, with no changes (`stashed=False`), with message, `-u` includes untracked, not-a-repo errors. `TestToolRegistration` parametrizes over all 7 git tools now.

**Test count: 298 → 321** (+23). All gates green.

#### Phase 1 Slice 6 — Language-aware `run_tests` tool
- `quoriv.tools.tests` — new module with one `@tool` callable `run_tests(framework=None, path=None, cwd=".")` that auto-detects the project's test framework from marker files and runs the suite via `subprocess.run` (`shell=False`, list args, cwd-bound).
- Detection (in order — first match wins, so a polyglot repo with both `pyproject.toml` and `package.json` defaults to Python, matching Quoriv's own layout):
  - `pyproject.toml` / `pytest.ini` / `setup.cfg` → `pytest`
  - `package.json` → `npm test`
  - `Cargo.toml` → `cargo test`
  - `go.mod` → `go test ./...`
- Command construction (`_build_command`): each framework gets its idiomatic invocation. `pytest -q`, `npm test --silent`, `cargo test`, `go test ./...`. Path scoping uses the framework's native convention — positional arg for pytest, after `--` for npm/cargo, replaces `./...` for go.
- Returns `{framework, command, exit_code, passed, stdout, stderr}` on success. The structured shape lets the LLM check `passed: bool` without parsing free-form output. On failure (no detection, cwd missing, unrecognized override, runner binary not on PATH) returns `{"error": "..."}` plus the attempted `framework` / `command` when known, so the agent can surface what was tried.
- `quoriv.tools.__init__` registers `run_tests` in `QUORIV_TOOLS` and re-exports it. `run_tests` deliberately stays outside `GIT_WRITE_TOOLS` — it executes a runner locally without mutating repo state; the session's existing shell-execution gate applies via DeepAgents' `execute` if the underlying runner shells out further.
- 29 new tests in `tests/unit/tools/test_runner.py`:
  - `TestDetectFramework` (8) — each marker file maps to the right framework, empty dir returns None, polyglot tie-break favors Python.
  - `TestBuildCommand` (9) — default + with-path for each framework, unknown framework raises `ValueError`.
  - `TestRunTests` (10) — passes / failure-sets-passed-false, framework override (works even with no marker files), path scoping for pytest, no-framework-detected error, unknown-framework override error, nonexistent cwd error, runner-binary-missing error (with `framework` + `command` echo), subprocess called with resolved absolute cwd, `shell=` never set (subprocess defaults to `shell=False`).
  - `TestToolRegistration` (2) — `run_tests` is a BaseTool with the right name and is present in `QUORIV_TOOLS`.

Slice 6b (parsed test-count summary from each runner's output) is deferred.

**Test count: 321 → 350** (+29). All gates green.

#### Phase 1 Slice 8 — Status line + introspection slash commands
- `quoriv.app` — persistent `bottom_toolbar` wired into the `PromptSession`. New pure helper `_build_status_line(model_id, mode, cwd, thread_id)` returns the formatted bar:

      <model_id> | mode=<mode> | <cwd basename> | thread=<first-8-chars>

  Bottom-bar callable closes over the loop's `thread_id` so `/clear` / `/load` / `/resume` rotations are reflected on the next prompt without any extra plumbing.
- Four new read-only slash commands wired through `_handle_slash` (now accepting keyword-only `model_id` / `cwd` / `mode` with safe defaults so legacy call sites and prior-slice tests still type-check):
  - `/tools` — lists DeepAgents built-ins (`write_todos`, `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`, `task`) under one heading and `QUORIV_TOOLS` (`find_symbol`, `git_*`, `run_tests`) under another, each with a one-line description.
  - `/memory` — shows status of `~/.quoriv/memory.md` (global) and `<cwd>/PROJECT.md` (project): which exist + byte size, with a hint when neither is present. These are the files DeepAgents' `MemoryMiddleware` will load once `build_agent` wires `memory=[...]` in a later slice.
  - `/mode` — prints the active permission mode, its description, the current `interrupt_on_for_mode(mode)` tool list (so the user sees exactly which tools will prompt), and the full available-modes table with the current one marked. Includes a hint that live-switching needs `quoriv chat --mode <name>` for now.
  - `/cost` — explicit stub pointing at Slice 9 (token tracking arrives with the local JSON trace log).
- `_handle_slash` dispatch extended with the four new commands. The function gained keyword-only `model_id` / `cwd` / `mode` parameters with defaults; `_interactive_loop` now also takes `model_id` / `cwd` and threads them into both the toolbar closure and the slash dispatcher.
- `SLASH_COMMANDS` table extended so `/help` lists every new entry.
- Two new module-level tables provide the source-of-truth descriptions: `_DEEPAGENTS_BUILTIN_TOOLS` (9 entries) and `_MODE_DESCRIPTIONS` (4 entries, keyed by `PermissionMode` Literal).
- 10 new tests in `tests/unit/test_app_slash.py`:
  - `TestSlice8SlashCommandsListed` (1) — all four new commands appear in `SLASH_COMMANDS`.
  - `TestToolsCommand` (1) — output names representative built-ins (`write_todos`) and Quoriv tools (`git_status`, `run_tests`) under their respective headings.
  - `TestMemoryCommand` (2) — empty-cwd reports "No memory files found"; `PROJECT.md` is detected and its byte count is shown.
  - `TestModeCommand` (3) — `ask` mode lists every gated tool (including the git writes from Slice 5b); `yolo` mode reports nothing-gated; the available-modes table is always rendered.
  - `TestCostCommand` (1) — output names the Slice 9 deferral plainly so the user knows where token tracking lands.
  - `TestBuildStatusLine` (2) — pure-function checks: every field appears, `thread_id` is truncated to 8 chars, and the delimiter shape is stable for edge-case paths.

**Test count: 350 → 360** (+10). All gates green.

#### Phase 1 Slice 9 — Local JSONL trace log + token-aware `/cost`
- `quoriv.observability.trace` — new module with `TraceLogger`. Append-only JSONL writer per chat thread; lazy file creation (no on-disk artifact until first write); `_sanitize()` recursively coerces non-JSON-native values (Path, dataclasses, sets, arbitrary objects via `str()`) so unserializable values never raise. Public API: `path` property, `log(event, **fields)`, `read_events()`, `token_totals()`. `read_events()` tolerates corrupt lines and non-dict JSON values (skipped silently — a single bad line never poisons the log). `token_totals()` sums across every `model_complete` event with sensible fallback (`input + output` when `total_tokens` is absent).
- `quoriv.core.persistence` — new `trace_path(cwd, thread_id)` and `traces_dir(cwd)` helpers, both re-exported from `quoriv.core`. Canonical location: `<cwd>/.quoriv/traces/<thread_id>.jsonl`. Mirrors the `db_path` / `registry_path` pattern from Slice 7.
- `quoriv.app` — `_interactive_loop` now owns a `TraceLogger`. The logger rotates alongside `thread_id` when `/clear` / `/load` / `/resume` switch threads (old log file remains on disk so a future `/load` can return to it and see its history). `_drive_turn` brackets the turn with `turn_start` / `turn_end` events; `_stream_events` records `model_complete` (with `input_tokens` / `output_tokens` / `total_tokens` extracted from the final `AIMessage.usage_metadata` when LangChain provides it), `tool_start` (with args), and `tool_end` (with output preview, truncated at 500 chars).
- `/cost` is no longer a stub — it reads `tracer.token_totals()` for the active thread and prints aligned counts plus the trace file path. Surface still notes that per-provider dollar-cost calculation is deferred (waiting on a rate table).
- `_handle_slash` gained a keyword-only `tracer: TraceLogger | None = None` parameter, defaulted so existing test calls without a tracer still type-check. When `None`, `/cost` falls back to a "no logger attached" message.
- 28 new tests:
  - `tests/unit/observability/test_trace.py` (24): `TestSanitize` (7) — primitives passthrough, dict recursion, Path coercion, dataclasses, sets/tuples, fallback to `str()`, non-string dict keys. `TestTraceLoggerWrites` (7) — `.path` property, lazy file creation, parent-dir auto-creation, JSONL append, ISO-8601 UTC timestamps, supplied fields preserved, unserializable values sanitized. `TestTraceLoggerReads` (4) — missing-file empty list, round trip, malformed-line resilience, non-dict JSON skipped. `TestTokenTotals` (5) — empty log zeros, multi-event sum, `total_tokens` fallback from `input + output`, ignores non-`model_complete` events, ignores non-int token fields. `TestTracePathIntegration` (2) — canonical filesystem location, round-trip through a fresh logger instance.
  - `tests/unit/test_app_slash.py` (4) — `TestCostCommand` rewritten: no-tracer reports "No trace logger"; empty log reports zero calls + trace file path; populated log shows token totals (input/output/total/calls); trace file path always surfaced.

**Test count: 360 → 388** (+28). All gates green.

#### Phase 1 Slice 6b — Parsed pytest counts in `run_tests`
- `quoriv.tools.tests._parse_pytest_summary` — new pure helper that extracts `{passed, failed, errors, skipped, duration_seconds}` from the terminal summary line emitted by pytest. Regex anchors on the `"in <duration>s"` suffix so unrelated `===` separator lines never match; the last match in the output wins so per-session header lines do not pollute the result. Returns the all-`None` shape when no summary line is found — the caller can tell "couldn't parse" (e.g., pytest crashed at collection) from "0 of everything".
- `run_tests` return shape gains a `summary` block with the parsed fields when `framework == "pytest"`. Other frameworks get the placeholder all-`None` summary until Slice 6c lands cargo / go / npm parsers — keeping the shape stable lets the LLM check `summary["passed"]` once instead of branching per framework.
- Parser reads `stdout + stderr` concatenated so CI environments that redirect pytest output to stderr still get counts.
- 13 new tests in `tests/unit/tools/test_runner.py`:
  - `TestParsePytestSummary` (9) — passing-only, failed-only, mixed (passed/failed/errors), passed+skipped, `"no tests ran"`, plural `"errors"`, no-summary-line returns all-None, empty input returns all-None, last-match-wins when multiple `===` lines.
  - `TestRunTests` (4 new) — pytest summary surfaces counts on the result dict; stderr summary parsed; pytest with no summary line returns null counts; non-pytest framework gets the all-None placeholder.

**Test count: 388 → 401** (+13). All gates green.

#### Phase 1 Slice 9c — Per-provider dollar-cost estimates in `/cost`
- `quoriv.observability.cost` — new module with the shipping rate table for `/cost`:
  - `ProviderRate` — frozen dataclass `{input_per_1k: float, output_per_1k: float}` (USD).
  - `RATES: dict[str, ProviderRate]` — 17 entries keyed by `provider:model` prefix. OpenAI (`gpt-5`, `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`), Anthropic (`claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4`, `claude-3-5-sonnet`, `claude-3-5-haiku`, `claude-3-opus`, `claude-3-haiku`), Gemini (`gemini-1.5-pro`, `gemini-1.5-flash`), and local sentinels (`ollama:`, `vllm:` → free).
  - `lookup_rate(model_id)` — longest-prefix match so `"openai:gpt-4o-mini"` resolves to its own entry rather than the broader `"openai:gpt-4o"`; versioned ids like `"openai:gpt-4o-2024-08-06"` fall back to the prefix.
  - `estimate_cost(rate, input_tokens, output_tokens)` — returns `{input_cost_usd, output_cost_usd, total_cost_usd}` from the per-1k rate.
- `quoriv.observability.__init__` re-exports `RATES`, `ProviderRate`, `lookup_rate`, `estimate_cost`.
- `/cost` is no longer dollar-blind. `_handle_cost` gained a keyword-only `model_id` parameter, threaded through `_handle_slash`. When the model has a rate, output now includes an "Estimated cost" block with input/output/total dollar amounts to 4-decimal precision. When no rate is configured, a friendly "update `quoriv.observability.cost.RATES`" hint is printed alongside the token totals — the agent still gets actionable info without a stale or fabricated dollar figure.
- 20 new tests:
  - `tests/unit/observability/test_cost.py` (17): `TestProviderRate` (2) — frozen + value equality. `TestRatesTable` (5) — non-empty, every entry is `ProviderRate`, no negative rates, every known provider (openai/anthropic/gemini/ollama) has at least one row, every key contains a colon. `TestLookupRate` (6) — exact match, longest-prefix wins, versioned suffix falls back to the prefix, ollama sentinel matches every model, unknown provider returns `None`, empty id returns `None`. `TestEstimateCost` (4) — zero tokens, basic math, sub-thousand tokens, free rate zeros out.
  - `tests/unit/test_app_slash.py` (3 new in `TestCostCommand`): known model shows dollar estimate with provider id; unknown model shows "No rate configured for ... — update RATES"; ollama renders `$0.0000`.

**Test count: 401 → 421** (+20). All gates green.

#### Phase 1 Slice 6c — cargo / go / npm output parsers
- `quoriv.tools.tests` extended with three pure helpers that mirror `_parse_pytest_summary`'s contract — input = combined stdout+stderr, output = `{passed, failed, errors, skipped, duration_seconds}` with the all-`None` fallback when nothing matches:
  - `_parse_cargo_summary` — matches `test result: ok. N passed; M failed; K ignored; ...; finished in Xs` lines (one per test binary). Multi-crate workspaces produce multiple summary lines; counts and durations are summed across all of them. `ignored` maps to `skipped`. cargo doesn't distinguish errors from failures so `errors` is always 0.
  - `_parse_go_summary` — counts per-test status lines (`--- PASS:` / `--- FAIL:` / `--- SKIP:`) for the count fields, and sums per-package summary durations (`ok pkg X.XXs` / `FAIL pkg X.XXs`). When only one or the other appears, the absent fields stay None or 0 in a documented way.
  - `_parse_npm_summary` — parses jest / vitest-style summary blocks (`Tests: N passed, M failed, K total` + `Time: X.XX s`). vitest's `todo` / `pending` categories collapse into `skipped` to keep the cross-runner shape stable. Other npm runners (mocha, ava, …) fall through to the all-`None` shape — they emit summaries in different formats and aren't covered by this slice.
- `_FRAMEWORK_PARSERS` dispatch dict replaces the `if chosen == "pytest"` branch in `run_tests`. Adding a new framework now means adding a marker file, command builder, and parser entry — all three concerns sit next to each other in the module.
- The all-`None` fallback still applies when a framework's runner emits output that doesn't match the expected summary shape (e.g., cargo compile error before tests run), so the caller can still tell "couldn't parse" from real zero counts. The Slice 6b test that exercised the placeholder path was renamed and rewritten to assert this contract under the new parsers.
- 16 new tests in `tests/unit/tools/test_runner.py`:
  - `TestParseCargoSummary` (4) — single-package success, single-package failure, multi-package counts + duration sum, no-summary returns all-None.
  - `TestParseGoSummary` (4) — `--- PASS / FAIL / SKIP` counts with package-duration sum, package-summary-only zero counts but non-None duration, multiple passes only (no package summary → duration stays None), no-recognisable-output returns all-None.
  - `TestParseNpmSummary` (5) — jest-style full summary, passing-only, `todo` + `pending` collapse to `skipped`, no-summary returns all-None, no `Time:` line keeps duration None.
  - `TestRunTests` (3 new) — each new framework dispatches to its own parser end-to-end through `run_tests`.

**Test count: 421 → 437** (+16). All gates green.

#### Phase 1 Slice 4b — Tree-sitter multi-language symbol intelligence
- Migrated the `ast` extra from the abandoned `tree-sitter-languages` (no Python 3.13 wheels) to the maintained `tree-sitter-language-pack>=0.6.0` and bumped `tree-sitter>=0.24.0`. The new pack ships bundled C wheels for Python 3.10-3.13 on Linux / macOS / Windows and covers ~80 languages.
- `quoriv.repo.ast` — new module: `LANGUAGE_BY_EXTENSION` (40+ entries), `detect_language(path)` by suffix, `get_parser(language)` lazy-loaded from the pack, `is_available()` so callers without the extra installed degrade gracefully. The lazy imports keep the rest of Quoriv working when someone installs without `[ast]`.
- `quoriv.repo.symbols` — new module with `Symbol` frozen dataclass and two public functions: `extract_definitions(source, language, *, target=None)` and `find_references(source, language, target)`. Per-language `DEFINITION_KINDS` maps tree-sitter node kinds to Quoriv symbol kinds for python / javascript / typescript / tsx / go / rust / java / kotlin / c / cpp / csharp / ruby / php / lua / elixir / swift. `CONTAINER_KINDS` tracks scopes (class / struct / trait / impl / module / namespace / protocol / interface / enum) so nested method definitions record their `parent`. Uses direct tree walks (not `QueryCursor`) because the language pack ships its own `Node` class that's binary-incompatible with the public `tree_sitter` Query API.
- `quoriv.tools.ast_tools` expanded:
  - `find_symbol` is now multi-language. Python (`.py` / `.pyi`) keeps the stdlib `ast` path (no extra needed); every other extension routes through tree-sitter via `quoriv.repo.symbols`.
  - New `@tool` callables: `go_to_definition(name, path=".")` — strict alias of `find_symbol` named for the agent's "jump-to-def" intent; `find_references(name, path=".")` — every identifier-like node whose text equals `name` (definition + callers + type uses + field accesses).
  - `_iter_source_files` walks the path, skipping common build / vendor dirs (`.venv`, `venv`, `__pycache__`, `.git`, `build`, `dist`, `node_modules`, `target`).
- `QUORIV_TOOLS` now exposes 11 tools: `find_symbol`, `go_to_definition`, `find_references`, the 7 git tools, and `run_tests`.
- 63 new tests across three files:
  - `tests/unit/repo/test_ast.py` (26) — extension → language for 21 file types, table sanity, case insensitivity, parser smoke tests for python/go, unknown language → `LookupError`.
  - `tests/unit/repo/test_symbols.py` (14) — Symbol frozenness, table coverage, Python def/class/method extraction with parent, Python reference search hits both def and call sites, Go type/method/function extraction, Go reference search across declarations and uses, TypeScript interface/type/class/method/function, Rust struct/trait/impl/function, graceful empty-list for unsupported languages.
  - `tests/unit/tools/test_ast_tools.py` (23 new) — `TestFindSymbolMultiLanguage` (5) covers go/ts/rust + `node_modules` / `target` skip + a mixed-language file tree. `TestGoToDefinition` (3) verifies alias semantics + registration. `TestFindReferences` (6) covers Go callsites, TS field access, empty/missing cases, registration.

**Test count: 437 → 500** (+63). All gates green.

#### Phase 1 Slice 9d — Config-driven cost rates
- `quoriv.config.schema` — two new Pydantic v2 models: `CostRate` (USD per 1,000 tokens with `Field(..., ge=0.0)` on both `input_per_1k` and `output_per_1k`) and `CostConfig` (`rates: dict[str, CostRate]`, defaults to empty). Both carry `extra="forbid"` so a typo in `~/.quoriv/config.toml` fails loudly at validation time. `QuorivConfig` gains a `cost: CostConfig = Field(default_factory=CostConfig)` section.
- `quoriv.observability.cost.effective_rates(config) -> dict[str, ProviderRate]` — merges the user's `cost.rates` over a fresh copy of the built-in `RATES`. The built-in table is never mutated; the returned dict is fresh each call. `effective_rates(None)` returns a copy of `RATES` so callers without a config object still get the standard table.
- `quoriv.observability.cost.lookup_rate` gained an optional second `rates` argument. Passing `None` falls back to the built-in `RATES` (legacy behaviour preserved). Passing the result of `effective_rates(config)` means longest-prefix lookup operates over the merged table — a user's fine-grained `anthropic:claude-opus-4-7` entry naturally wins over the broader built-in `anthropic:claude-opus-4` prefix.
- `quoriv.observability.__init__` re-exports `effective_rates`.
- `quoriv.app.run_chat` precomputes `cost_rates = effective_rates(config)` once per session and threads it through `_interactive_loop` → `_handle_slash` → `_handle_cost`. The new keyword-only `cost_rates` parameter carries a `None` default on every layer so older test entry points keep working.
- The "no rate configured" hint in `/cost` now points the user at `[cost.rates."{provider}:{model}"]` in `~/.quoriv/config.toml` rather than at the in-source `RATES` dict, matching the new override path.
- `config.example.toml` — documents the `[cost.rates."provider:model"]` block with example overrides, the non-negative-float constraint, and the longest-prefix lookup rule.
- 20 new tests:
  - `tests/unit/config/test_schema.py` `TestCostConfig` (8) — empty defaults, `QuorivConfig.cost.rates == {}`, rate accepts 0.0, rate rejects negative input / output, missing fields rejected, extra fields rejected on both `CostRate` and `CostConfig`, full round-trip through `QuorivConfig.model_validate`.
  - `tests/unit/observability/test_cost.py` `TestLookupRateCustomTable` (3) — uses supplied table not built-in, longest-prefix within custom table, explicit `None` falls back to built-in.
  - `tests/unit/observability/test_cost.py` `TestEffectiveRates` (6) — `None` returns a built-ins copy that is safe to mutate, empty config matches built-ins, user override replaces built-in by key (other entries survive), user can add a new provider, calling `effective_rates` does not mutate `RATES`, a more specific user key wins over a broader built-in prefix via merged-table longest-prefix.
  - `tests/unit/test_app_slash.py` `TestCostCommand` (3 new) — user rate override shadows the built-in (1k input @ $0.05 + 1k output @ $0.20 → totals appear in `/cost`); user rate can add an unknown model so a previously rateless id now renders an estimate; legacy "No rate configured" hint absent when an override exists.

**Test count: 500 → 520** (+20). All gates green.

#### Phase 1 Slice 8b — Live `/mode` switch
- `/mode <name>` now rebuilds the compiled DeepAgent in place against the same `AsyncSqliteSaver` checkpointer. The running thread's conversational state survives the switch — only the `interrupt_on=` dict changes (via `interrupt_on_for_mode(new_mode)`). No restart, no new thread id.
- `quoriv.app._SlashResult` gained a third slot, `new_mode: PermissionMode | None`. The interactive loop branches on it after a slash dispatch: when set, it calls `build_agent(config, model_override=..., cwd=..., mode=new_mode, checkpointer=saver)` and reassigns the local `agent`. The `_toolbar` closure reads the latest `permission_mode` at call time, so the status line reflects the new mode on the next prompt redraw without explicit refresh.
- `_handle_mode` is now mode-aware: with no argument it preserves the Slice 8 display (current mode + gated tools + menu); with an argument it normalises to lowercase, validates against `ALLOWED_MODES`, short-circuits on same-mode requests with a friendly `"Already in <mode>"` note, and surfaces unknown values with the valid set listed inline. The closing line of the display variant now reads `Switch live with /mode <name>` instead of the stale `Live-switch lands in a later slice.`
- `quoriv.app.run_chat` and `_interactive_loop` thread `config`, `model_override`, and the open `AsyncSqliteSaver` through as keyword-only args. All three default to `None` so legacy single-mode test entry points keep working without modification.
- `SLASH_COMMANDS["/mode"]` description updated from `"Show the current permission mode and what each mode gates"` to `"Show permission mode (no arg) or live-switch (/mode <name>)"` so `/help` advertises the new form.
- 6 new tests in `tests/unit/test_app_slash.py::TestModeCommand`:
  - `test_no_arg_does_not_switch` — display-only path returns `_SlashResult(new_mode=None)`.
  - `test_valid_arg_returns_new_mode` — `/mode yolo` from `ask` returns `_SlashResult(new_mode="yolo")` silently (the loop, not the handler, prints the confirmation).
  - `test_valid_arg_with_uppercase_normalized` — `/mode YOLO` normalises to `"yolo"`.
  - `test_same_mode_does_not_switch` — `/mode ask` while in `ask` prints `"Already in"` and returns no switch.
  - `test_invalid_arg_reports_error` — `/mode banana` prints the unknown-mode error with the offending input and the full valid set; returns no switch.
  - `test_all_modes_can_be_targets` — round-trips every valid mode as a target from a different starting mode to catch any `PermissionMode` literal-narrowing regression in the dispatch path.

**Test count: 520 → 526** (+6). All gates green.

#### Phase 1 Slice 9b — End-to-end stubbed-LLM turn test
- `tests/integration/test_e2e_stubbed_chat.py` — first integration test: drives a full user turn through `quoriv.app._drive_turn` against a real `build_agent`-compiled DeepAgent whose model is a `_StubChatModel` (a `langchain_core.language_models.fake_chat_models.GenericFakeChatModel` subclass with `bind_tools` short-circuited to `self`, since the base class raises `NotImplementedError` and DeepAgents binds tools at compile time). `quoriv.core.agent.get_model` is monkeypatched to return the stub, so the test exercises the same code path the CLI uses — including the LangGraph event stream, the `StreamRenderer` `Live`, the `TraceLogger` writes, the `MemorySaver` checkpointer, and the `PathProtectionMiddleware`. Mode is `yolo` to skip HITL interrupts so the agent finishes in one model turn.
- 4 tests in `TestEndToEndTurn`:
  - `test_drive_turn_writes_turn_start_and_end` — verifies the trace bracket: first record is `turn_start` with the original `thread_id`/`user_input`/`mode`, last record is `turn_end` with the matching `thread_id`. That bracket is the contract `/cost` and any future observability tooling depend on.
  - `test_drive_turn_records_model_complete` — verifies at least one `model_complete` record lands per turn (one stub `AIMessage` → one `on_chat_model_end` → one trace entry).
  - `test_drive_turn_renders_stub_response` — sanity that the LLM payload is actually rendered to the console buffer through `StreamRenderer`, not just traced.
  - `test_status_line_built_from_session_context` — `_build_status_line(model_id, mode, cwd, thread_id)` is unaffected by a completed turn and still returns a well-formed string with the expected fields, mode marker, truncated thread id, and three separators.
- Catches future regressions where `_drive_turn` / `_stream_events` / `TraceLogger` drift out of sync — a renamed LangGraph event key, a missing tracer call, or a status-line format change all surface here instead of in production.

**Test count: 526 → 530** (+4). All gates green. With Slice 9b done, Phase 1 is complete.

#### Phase 2 Slice 1 — Memory wiring
- `quoriv.core.memory` — new module: `MemoryCandidate` NamedTuple (`label`, `path`), `memory_candidates(cwd)` returning the ordered list of two candidates (global first as `~/.quoriv/memory.md`, project second as `<cwd>/PROJECT.md`), and `resolve_memory_files(cwd)` filtering to ones that exist via `Path.is_file()` (so a directory named `PROJECT.md` is correctly rejected). The order matters: DeepAgents concatenates the list in load order under `<agent_memory>` in the system prompt, so global-then-project lets a project file refine a global note — same precedence rule the TOML loader uses.
- `quoriv.core.agent.build_agent` now calls `resolve_memory_files(root)`, converts to strings, and passes the result to `create_deep_agent(memory=...)`. When the resolved list is empty, the argument is `None` — DeepAgents documents `None` (not `[]`) as the contract for "don't attach the middleware", so we honor that.
- `quoriv.core.__init__` re-exports `MemoryCandidate`, `memory_candidates`, `resolve_memory_files`.
- `quoriv.app._handle_memory` rewritten to source its candidate list from `memory_candidates(cwd)` rather than hardcoded paths. Each present file now gains a `(loaded)` tag, making it clear the agent's `MemoryMiddleware` has actually seen the file — not just that it exists on disk.
- `quoriv.app._render_welcome` adds a `Memory: PROJECT.md, memory.md` line to the welcome panel when at least one file is loaded; silent when neither exists so first-time users don't see clutter.
- 19 new tests:
  - `tests/unit/core/test_memory.py` (10): `TestMemoryCandidates` (5) — load-order, global path uses fake_home/.quoriv, project path tracks the supplied cwd, NamedTuple round-trip, different cwds yield different project paths. `TestResolveMemoryFiles` (5) — neither / project-only / global-only / both / directory-with-the-name rejected.
  - `tests/unit/core/test_agent.py::TestBuildAgentMemoryWiring` (4) — monkeypatched `create_deep_agent` captures kwargs and verifies `memory=None` when no files, `memory=[...PROJECT.md]` when only project file present, `memory=[...memory.md]` when only global, and global-then-project ordering when both exist.
  - `tests/unit/test_app_slash.py::TestMemoryCommand` (2 new) — `(loaded)` tag appears next to present files; absent files do not show the tag. The two pre-existing `/memory` tests gained the `fake_home` fixture so a developer's real `~/.quoriv/memory.md` doesn't leak into the assertion.
  - `tests/unit/test_app_slash.py::TestWelcomePanel` (3) — no memory line when neither file present; PROJECT.md surfaces in the panel; global memory.md surfaces.

**Test count: 530 → 549** (+19). All gates green.

#### Phase 2 Slice 2 — `quoriv init`
- New `quoriv init [PATH]` command in `quoriv.cli` scaffolds a starter `PROJECT.md` at the target directory (defaults to `cwd`). Refuses to overwrite an existing file by default — exits non-zero with a "pass `--force` to overwrite" hint so a CI script can't silently nuke a hand-edited `PROJECT.md`. `--force` / `-f` overrides.
- `quoriv.core.memory.PROJECT_MEMORY_TEMPLATE` — the starter content. One-screen template: top-level note explaining what Quoriv does with the file, then sections for `Project overview`, `Architecture`, `Conventions`, `Useful commands`, `Things to avoid`. Designed to fit on one screen so users can scan the shape before editing.
- Removed an outdated `# noqa: TC003` on `from pathlib import Path` in `cli.py` — the import is now used at runtime by the new `init` command's `Path` arguments and `Path.cwd()` fallback, not just in type annotations.
- 6 new tests in `tests/unit/test_cli.py::TestInit`:
  - `test_creates_project_md_in_target_dir` — happy path with explicit PATH; "Created" message; file lands at `<dir>/PROJECT.md`.
  - `test_refuses_to_overwrite_by_default` — pre-existing `PROJECT.md` survives untouched; exit code non-zero; output mentions `--force`.
  - `test_force_overwrites_existing` — `--force` replaces the file; "Overwrote" message; old content gone; new content carries the template header.
  - `test_force_short_flag` — `-f` short form works the same as `--force`.
  - `test_template_covers_expected_sections` — guards the UX of the starter: all six headings must be present (regression catcher for an accidental template gut).
  - `test_no_path_writes_to_cwd` — without an argument, writes to `Path.cwd()` (monkeypatched to `tmp_path` because Typer's `CliRunner` doesn't chdir).
- `TestTopLevel::test_help_lists_commands` updated to include `init` in the expected command list.

**Test count: 549 → 555** (+6). All gates green.

#### Phase 2 Slice 3 — "Always allow" session allowlist
- `quoriv.permissions.allowlist` — new module: `SessionAllowlist`, an in-memory set of tool names the user has promoted from a one-time HITL approval to a session-persistent one. ``__contains__``, ``allow``, ``clear``, ``__len__``, ``tools()`` returning an immutable ``frozenset`` snapshot. Keyed by tool name only (matches the granularity ``interrupt_on=`` itself uses).
- `quoriv.ui.prompts.DecisionType` gained `"approve_always"`. The interactive prompt now reads `approve / reject / always [a/r/A]`. `parse_choice` accepts `A`, `aa`, and the spelled-out `always` (case-insensitive) for the new decision; bare lowercase `a` still means "approve once" so a user can't accidentally promote a tool by typing the same key as before.
- `quoriv.app._collect_decisions` consults the allowlist before calling `prompt_approval`: matching tools auto-resolve to `approve` with a `[dim]auto-approved <tool> (allowlisted this session)[/dim]` note. When the user picks `approve_always`, the tool name is added to the allowlist and a `[green]Will auto-approve …[/green]` confirmation is rendered. ``auto_deny`` (read-only mode) always wins over the allowlist — a remembered approval doesn't unlock read-only.
- `quoriv.app._decision_payload` maps `approve_always` → `{"type": "approve"}` on the wire. DeepAgents only speaks `approve` / `reject` / `edit` / `respond`; the allowlist promotion is a Quoriv UX layer.
- `quoriv.app._interactive_loop` creates one `SessionAllowlist` per `run_chat` invocation and threads it through `_drive_turn` → `_collect_decisions`. Survives `/clear` (the user promoted these tools deliberately; rotating the thread shouldn't silently un-promote them).
- 21 new tests:
  - `tests/unit/permissions/test_allowlist.py::TestSessionAllowlist` (7) — empty default, `allow` adds, idempotency, `__contains__` tolerates non-strings, `tools()` returns an immutable snapshot, `clear`, independent multi-tool tracking.
  - `tests/unit/ui/test_prompts.py::TestParseChoice::test_approve_always_aliases` (1 parametrized × 6 inputs) — covers `A`, `aa`, `always`, `Always`, `ALWAYS`, and whitespace-padded forms. The `test_approve_aliases` parametrize lost the bare `"A"` entry, since capital `A` is now reserved for `approve_always`; the comment in-place documents the split.
  - `tests/unit/test_app_decisions.py` (9) — `TestDecisionPayload` (3): approve passthrough, reject keeps message, approve_always → approve. `TestCollectDecisionsAllowlist` (6): allowlisted tool skips prompt; non-allowlisted still prompts; approve_always promotes; second call uses the promoted entry (single prompt across two calls); `auto_deny` wins over allowlist; `None` allowlist preserves legacy "always prompt" behavior.

**Test count: 555 → 576** (+21). All gates green.

#### Phase 2 Slice 4 — Per-task model routing (built-in subagents)
- `quoriv.core.subagents` — new module: three built-in `SubAgent` specs (`researcher`, `debugger`, `reviewer`) with fixed system prompts and a `build_subagents(config)` helper that resolves each role's configured model token (`"default"` / `"fast"` / `"strong"` / a literal `"provider:name"`) into a model instance via `quoriv.models.factory.get_model`. Going through the Quoriv factory rather than letting DeepAgents call `init_chat_model` directly keeps the keychain-aware key lookup consistent across the main agent and every subagent.
- `quoriv.config.schema` — new `SubAgentRoleConfig` (`model: str = "default"`) and `SubAgentsConfig` (`researcher` / `debugger` / `reviewer`, with defaults `"fast"` / `"strong"` / `"strong"`). `extra="forbid"` on both — invented role names and stray fields fail fast at validation. Added to `QuorivConfig` as the `subagents` section.
- `quoriv.core.agent.build_agent` now calls `build_subagents(config)` and passes the result to `create_deep_agent(subagents=...)`. Returned shapes are typed as DeepAgents' `SubAgent` `TypedDict` via `cast` (imported under `TYPE_CHECKING` so the runtime import surface stays small).
- `config.example.toml` documents the new `[subagents.*]` blocks with the token taxonomy and per-role defaults.
- 16 new tests (and 1 integration-test fix):
  - `tests/unit/core/test_subagents.py::TestResolveModelToken` (5) — `default` / `fast` / `strong` resolve through `[model]`; literal `provider:name` passes through; overridden `[model]` section flows to all tokens.
  - `tests/unit/core/test_subagents.py::TestBuildSubagents` (6) — three roles in fixed order; every role carries name/description/system_prompt/model; researcher uses `model.fast` by default, debugger/reviewer use `model.strong` (verified by monkeypatching `quoriv.core.subagents.get_model` and capturing the requested ids); user can redirect a role to a literal model; user can redirect a role to `"default"`; role descriptions mention their job (the only signal the main agent has when routing).
  - `tests/unit/core/test_subagents.py::TestSubAgentsConfigSchema` (4) — default routing, partial-override preserves other roles, unknown role rejected, extra-field-within-role rejected.
  - `tests/unit/core/test_subagents.py::TestBuildAgentSubagentsWiring` (1) — `build_agent` passes a list of three subagents named `[researcher, debugger, reviewer]` into `create_deep_agent` (uses the same `create_deep_agent` capture pattern as the memory-wiring test).
  - `tests/integration/test_e2e_stubbed_chat.py` updated to monkeypatch *both* `quoriv.core.agent.get_model` and `quoriv.core.subagents.get_model`, since each subagent now resolves its own model. Existing 4 integration tests still pass unchanged.

**Test count: 576 → 592** (+16). All gates green.

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

### Coming next (Phase 2 — remaining slices)
- **Python plugin API:** setuptools entry points (`quoriv.plugins`) merged into the agent's `tools=`
- **MCP client:** `quoriv.plugins.mcp` over stdio + SSE transports

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
