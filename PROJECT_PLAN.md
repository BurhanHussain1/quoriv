# `Quoriv` — Complete Project Plan

> Open-source, terminal-based AI coding agent. Built in Python on **DeepAgents 0.6.1 + LangGraph**. Model-agnostic (OpenAI, Anthropic, Gemini, Ollama, vLLM). Inspired by Claude Code, Gemini CLI, and Aider — but locally-runnable, multi-provider, and fully extensible from day one.

> **Architecture revision (after auditing DeepAgents 0.6.1):** the agent runtime, file/shell/grep/todo/subagent/summarization/memory/HITL/permissions machinery is **all provided by DeepAgents**. Quoriv's scope is the CLI, TUI, config, Quoriv-specific tools (AST/git/web/tests/MCP), and the UX that wraps the compiled graph. See [`docs/DEEPAGENTS_REFERENCE.md`](docs/DEEPAGENTS_REFERENCE.md) for the full reuse map.

---

## 1. Project Description

`Quoriv` is an open-source, terminal-based AI coding agent that helps developers understand, edit, debug, and ship code through natural-language conversation directly inside their repository. Built in Python on top of [DeepAgents](https://github.com/langchain-ai/deepagents) and [LangGraph](https://github.com/langchain-ai/langgraph), it is model-agnostic by design — working with cloud APIs like OpenAI, Anthropic Claude, and Google Gemini, as well as fully private local models through Ollama and self-hosted vLLM endpoints — so users can choose between hosted intelligence and complete offline privacy.

Quoriv leans on DeepAgents for the entire agent runtime: planning, file operations, shell execution, sub-agents, context compaction, permission rules, memory loading, and human-in-the-loop approval are all handled by DeepAgents' built-in middleware. Quoriv's own code provides the CLI and TUI, the configuration layer, the OS keychain integration, multi-tier permission UX, Quoriv-specific tools (tree-sitter symbol navigation, git operations, language-aware test running, web search/fetch, MCP plugin support), and the Rich-based renderers for streaming output, diffs, and approval prompts.

---

## 2. Goals

### Primary goals
- Daily-driver coding assistant in any repository
- Open-source release under Apache 2.0
- Usable by individuals and small teams
- Works with both hosted APIs (OpenAI today, Anthropic / Gemini / OpenRouter / Together later) and local models (Ollama, vLLM)
- Extensible via MCP and a Python plugin API
- Persistent memory across sessions (via DeepAgents' AGENTS.md-spec loader)
- Safe by default through a multi-tier permission system that compiles down to DeepAgents `permissions=` + `interrupt_on=` config

### Non-goals (for v1.0)
- VSCode/JetBrains extension (architecture supports it later, but not shipped in v1)
- Web UI (same — supported by architecture, not shipped)
- Built-in cloud / SaaS offering
- Fine-tuning or training models
- Mobile clients
- Reimplementing anything DeepAgents already provides (see `docs/DEEPAGENTS_REFERENCE.md` for the explicit list)

---

## 3. Locked Design Decisions

| Area | Decision | Rationale |
|---|---|---|
| **Audience** | OSS release + team-usable | Apache 2.0 license is enterprise-friendly |
| **Architecture** | Monolithic Python CLI wrapping `create_deep_agent` | Simpler; internal seams allow extracting a server later |
| **Agent runtime** | DeepAgents 0.6.1 (compiled LangGraph) — not built by us | Already provides ~80% of what we'd otherwise build |
| **Reuse policy** | **No Quoriv module duplicates a DeepAgents feature.** See `docs/DEEPAGENTS_REFERENCE.md` for the reuse map. | Avoid drift between two implementations; benefit from upstream fixes |
| **Backend** | `LocalShellBackend(root_dir=cwd)` from DeepAgents | Real disk + real shell; matches "live in your terminal" UX |
| **Agent topology** | Single main agent + DeepAgents sub-agents on demand | Balanced cost vs capability |
| **Repo intel** | Grep + glob + read (DeepAgents' built-ins) **plus** tree-sitter AST tools (Quoriv-added) for symbol awareness | Best ratio of quality to effort; no embeddings/LSP for v1 |
| **Plugins** | Both MCP (external) + Python plugin API (internal) | Max flexibility, future-proof |
| **Sandbox** | No container; DeepAgents' `LocalShellBackend` + `permissions=` rules + `interrupt_on=` HITL | Simpler, faster, works on any OS |
| **Permission modes** | `read-only` / `ask` / `auto` / `yolo` — Quoriv translates each to DeepAgents `permissions=[]` + `interrupt_on={}` config | Multi-tier posture, single point of policy |
| **Path protection** | Always-on Quoriv layer denying writes to `.env`, `.git/`, `.ssh/`, etc., enforced via `FilesystemPermission` rules | Hard invariant, can't be disabled |
| **Model routing** | Per-task: small/cheap for trivial, large for hard — implemented by giving each `SubAgent` its own `model=` | Cuts cost dramatically; uses native DeepAgents mechanism |
| **Providers (Phase 1)** | OpenAI | What the user has access to today |
| **Providers (Phase 3)** | Anthropic, Gemini, Ollama, vLLM, OpenRouter | Provider factory ready in Phase 1 |
| **TUI library** | `rich` (chat-scroll) + `prompt_toolkit` (input) | What Claude Code / Gemini CLI use |
| **CLI framework** | `typer` | Clean ergonomics, type-driven |
| **Project memory** | `PROJECT.md` + `~/.quoriv/memory.md` loaded by DeepAgents `MemoryMiddleware` via `memory=[...]` parameter | DeepAgents owns the loader; we just point at the files |
| **Session persistence** | LangGraph `SqliteSaver` passed as `checkpointer=` to `create_deep_agent` | Standard mechanism; supports resume + HITL |
| **Storage** | SQLite (sessions/traces); TOML (config); markdown (memory) | Single file each, queryable, portable |
| **Distribution** | `pip install` first; PyInstaller binaries in Phase 4 | Lowest-friction path; binaries for non-Python users later |
| **Timeline** | 4 phases over ~3 months (revised down — DeepAgents reuse compresses Phase 1) | "Build it right" pacing |
| **License** | Apache 2.0 | OSS-friendly + enterprise-compatible |

---

## 4. Tech Stack

### Runtime
- **Python 3.11+** (3.12 preferred — better asyncio + error messages)
- **`deepagents` 0.6.1** — the agent runtime (not just "engine") — provides planning, file/shell/grep/todo tools, sub-agents, summarization, memory, HITL, permissions
- **`langgraph`** — included with deepagents; provides compiled state graph, streaming, checkpointing
- **`langchain`** + **`langchain-openai`** — provider adapters (Phase 1)
- **`langchain-anthropic`** / **`langchain-google-genai`** / **`langchain-ollama`** — Phase 3 providers
- **`mcp`** — official MCP Python SDK (Phase 2)

### UI
- **`rich`** — markdown rendering, syntax highlighting, tables, diff display
- **`prompt_toolkit`** — multi-line input box at the bottom of the chat
- **`typer`** — CLI commands and flags

### Data
- **`pydantic`** v2 — config schemas + tool argument validation
- **`pydantic-settings`** — env var integration
- **`aiosqlite`** — async SQLite for sessions and traces
- **`tomli` / built-in `tomllib`** — config file parsing
- **`keyring`** — OS keychain for API key storage

### Code understanding (Quoriv tools, layered on top of DeepAgents grep/glob)
- **`tree-sitter`** + **`tree-sitter-languages`** — AST for ~30 languages

### Plumbing
- **`httpx`** — async HTTP
- **`tenacity`** — retries with exponential backoff
- **`loguru`** — structured logging

### Dev
- **`ruff`** — lint + format
- **`mypy`** — type checking
- **`pytest`** + **`pytest-asyncio`** — testing
- **`pre-commit`** — git hooks
- **`mkdocs-material`** — docs site (Phase 4)
- **`pyinstaller`** — binaries (Phase 4)

---

## 5. Project Structure

Folders marked **DROPPED** were removed when we adopted the DeepAgents-reuse architecture; their responsibilities live in DeepAgents middleware/backends.

```
quoriv/                                      # repo root
├── pyproject.toml
├── README.md
├── LICENSE                                  # Apache-2.0
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── PROJECT_PLAN.md                          # this file (gitignored)
├── config.example.toml
├── .pre-commit-config.yaml
├── .gitignore
├── .github/
│   ├── workflows/
│   │   ├── test.yml
│   │   ├── release.yml
│   │   └── lint.yml
│   └── ISSUE_TEMPLATE/
├── docs/
│   ├── DEEPAGENTS_REFERENCE.md              # internal SDK reference
│   ├── index.md                             # MkDocs (Phase 4)
│   ├── installation.md
│   ├── configuration.md
│   ├── tools.md
│   ├── plugins.md
│   └── architecture.md
├── tests/
│   ├── unit/
│   ├── integration/
│   └── eval/                                # agent evals on real tasks
├── scripts/
│   ├── release.py
│   └── eval.py
└── src/quoriv/
    ├── __init__.py
    ├── __main__.py                          # python -m quoriv
    ├── cli.py                               # Typer app: top-level commands
    ├── app.py                               # Main interactive loop
    │
    ├── core/                                # WRAPS create_deep_agent
    │   ├── __init__.py
    │   ├── agent.py                         # build the compiled DeepAgent for a session
    │   ├── routing.py                       # per-task model routing via SubAgent specs
    │   └── events.py                        # LangGraph event subscriber for UI
    │   # DROPPED: runtime.py (DeepAgents IS the loop)
    │   # DROPPED: context.py (SummarizationMiddleware handles it)
    │
    ├── models/                              # Builds BaseChatModel for create_deep_agent
    │   ├── __init__.py
    │   ├── base.py                          # ModelSpec, ModelCapabilities
    │   ├── factory.py                       # get_model("openai:gpt-4.1")
    │   ├── openai.py                        # Phase 1
    │   ├── anthropic.py                     # Phase 3
    │   ├── gemini.py                        # Phase 3
    │   ├── ollama.py                        # Phase 3
    │   ├── vllm.py                          # Phase 3
    │   └── openrouter.py                    # Phase 3
    │
    ├── tools/                               # QUORIV-SPECIFIC TOOLS ONLY
    │   ├── __init__.py
    │   ├── ast_tools.py                     # tree-sitter: find_symbol, go_to_def, refs
    │   ├── git.py                           # status, diff, log, commit, blame
    │   ├── tests.py                         # language-aware test runner
    │   └── web.py                           # web_search, web_fetch
    │   # DROPPED: files.py — DeepAgents FilesystemMiddleware owns these
    │   # DROPPED: search.py — DeepAgents grep/glob owns these
    │   # DROPPED: shell.py  — LocalShellBackend.execute owns this
    │   # DROPPED: patch.py  — use DeepAgents edit_file
    │   # DROPPED: base.py   — use langchain_core.tools.tool decorator directly
    │
    ├── permissions/                         # Mode translation, NOT a guard layer
    │   ├── __init__.py
    │   ├── modes.py                         # 4-mode -> DeepAgents (permissions=, interrupt_on=)
    │   └── paths.py                         # always-on path protection rules
    │   # DROPPED: guard.py     — FilesystemMiddleware enforces at tool level
    │   # DROPPED: allowlist.py — Phase 2 (per-session "always allow" UX layer)
    │
    ├── plugins/
    │   ├── __init__.py
    │   ├── api.py                           # Python plugin API (entry-point loader)
    │   ├── loader.py                        # discover + load plugins
    │   └── mcp/
    │       ├── __init__.py
    │       ├── client.py                    # MCP client over stdio/SSE
    │       └── registry.py                  # connected servers
    │
    ├── ui/                                  # All terminal rendering — Quoriv-owned
    │   ├── __init__.py
    │   ├── chat.py                          # main scroll
    │   ├── stream.py                        # token-streaming renderer
    │   ├── diff.py                          # diff display
    │   ├── prompts.py                       # approval prompts for interrupt_on
    │   ├── slash.py                         # slash command dispatch
    │   ├── status.py                        # status line (model, tokens, $, branch)
    │   └── theme.py                         # color themes
    │
    ├── config/                              # DONE in Phase 0 Days 2-3
    │   ├── __init__.py
    │   ├── schema.py                        # Pydantic v2 settings
    │   ├── loader.py                        # merge global + project TOML
    │   └── keychain.py                      # OS keychain for API keys
    │
    ├── observability/                       # Cost + tracing
    │   ├── __init__.py
    │   ├── log.py                           # loguru config
    │   ├── cost.py                          # per-call cost tracking via LangChain callbacks
    │   ├── trace.py                         # local JSON trace export
    │   └── telemetry.py                     # opt-in only
    │
    └── repo/                                # Powers ast_tools (Quoriv tools)
        ├── __init__.py
        ├── ast.py                           # tree-sitter parsers per-language
        └── symbols.py                       # symbol lookup index
        # DROPPED: index.py — DeepAgents glob/grep covers basic file enumeration

# DROPPED entirely: src/quoriv/memory/
# Memory files (PROJECT.md, ~/.quoriv/memory.md) are user-managed text;
# DeepAgents MemoryMiddleware loads them via memory=[...] parameter.
```

**Why this shape:** `core/` package wraps DeepAgents into a session object that any client (CLI today, VSCode/web later) can drive. The CLI is just one consumer. `tools/` holds **only** what DeepAgents doesn't provide.

---

## 6. Architecture (high-level)

```
                       Terminal (Rich + prompt_toolkit)
                                    |
                              quoriv.cli (Typer)
                                    |
                              quoriv.app  (main loop)
                                    |
       +----------------------------+-----------------------------+
       |                            |                             |
   quoriv.ui                quoriv.core.agent           quoriv.observability
   (rendering)              (builds DeepAgent)          (cost, trace, log)
                                    |
                          +---------+----------+
                          |                    |
              deepagents.create_deep_agent  quoriv.models.factory
                          |                    |
                          |          (provides BaseChatModel)
                          v                    v
              +-----------+-----------+-----------+
              |   DeepAgents middleware stack    |
              |   - TodoListMiddleware           |   <- write_todos
              |   - FilesystemMiddleware         |   <- ls/read/write/edit/glob/grep
              |   - SubAgentMiddleware           |   <- task
              |   - SummarizationMiddleware      |   <- auto context compaction
              |   - MemoryMiddleware             |   <- AGENTS.md/PROJECT.md
              |   - HumanInTheLoopMiddleware     |   <- interrupt_on
              |   - AnthropicPromptCaching       |
              +-----------+----------------------+
                          |
              LocalShellBackend (real disk + shell)
                          |
              +-----------+-----------+
              | + Quoriv-added tools |
              |   - ast_tools         |
              |   - git               |
              |   - tests             |
              |   - web               |
              |   - MCP-loaded tools  |
              +-----------------------+

   quoriv.permissions.modes  -->  permissions=[FilesystemPermission(...)]
                                    interrupt_on={"edit_file": True, ...}
   quoriv.permissions.paths  -->  always-on .env/.git/.ssh denylist
```

DeepAgents' compiled LangGraph is the agent loop, the streaming event source, and the checkpointable state container. Quoriv lives around it: building it, driving it, rendering it.

---

## 7. Phased Build Plan (~3 months — revised down after reuse audit)

### Phase 0 — Foundation (~1 week)
**Goal:** the skeleton is ready, a "hello world" agent runs.

- ✅ Day 1: Repo init, `pyproject.toml`, license, README, CONTRIBUTING, SECURITY, CHANGELOG, `.gitignore`, `.pre-commit-config.yaml`, CI workflows
- ✅ Day 2: Folder skeleton (DeepAgents-revised), Pydantic v2 config schema, TOML loader (global + project merge)
- ✅ Day 3: `keyring` API key storage with env-var fallback, model factory + OpenAI provider — 74 tests passing
- ⬜ Day 4: Minimal `cli.py` (Typer with `chat`, `config`, `doctor` commands) + `app.py` (Rich chat loop) streaming an OpenAI response. **Still pre-DeepAgents** — direct LangChain streaming so we test the UI loop in isolation.
- ⬜ Day 5: Wire `create_deep_agent(model=..., backend=LocalShellBackend(root_dir=cwd))`. **Full tool suite available immediately** (ls/read/write/edit/glob/grep/execute/task/write_todos). Verify end-to-end agentic loop on a real task. **No custom Quoriv tools yet** — Day 5 just proves the DeepAgents integration works.

**Deliverable:** `quoriv chat` runs end-to-end with DeepAgents driving the full built-in toolset against the user's actual repo.

---

### Phase 1 — Quoriv UX + Quoriv-specific tools (~2–3 weeks, revised down)
**Goal:** a usable Claude-Code-like CLI for real work, with Quoriv's distinctive UX layer.

- **Permission modes** (`quoriv.permissions.modes` + `paths`):
  - Translate `read-only / ask / auto / yolo` to `permissions=[]` + `interrupt_on={}` dicts
  - Always-on path protection (`.env`, `.git/`, `.ssh/`, `secrets/`)
  - `--mode` CLI flag and `/mode` slash command
- **Rich TUI**:
  - Subscribe to `agent.astream_events(version="v2")` and render
  - Streaming markdown
  - Syntax-highlighted code blocks
  - Diff rendering for proposed edits (custom — DeepAgents emits the call, we render)
  - Approval prompts (UI for `interrupt_on` pauses) with arrow-key navigation
  - Slash commands: `/help` `/clear` `/model` `/cost` `/tools` `/mode` `/save` `/load` `/doctor`
  - Status line: model, tokens used, cost, git branch
- **Quoriv-specific tools** (added as plain functions in `tools=[]`):
  - Tree-sitter AST tools: `find_symbol`, `go_to_definition`, `find_references`
  - Git tools: `git_status`, `git_diff`, `git_log`, `git_blame` (write ops gated by interrupt_on)
  - Test runner: language-detected `run_tests` (pytest/jest/cargo/go)
- **Session persistence**: `SqliteSaver` wired to `checkpointer=`
- **Local trace log** (JSON) — every model call + tool call
- **Tests**: unit per Quoriv tool, integration against the compiled graph

**Deliverable:** usable daily for real coding tasks. Streaming, diffs, approvals, and Quoriv-specific tools all work.

---

### Phase 2 — Memory wiring, routing, plugins (~2–3 weeks, revised down)
**Goal:** the agent feels personalized and is extensible.

- **Memory wiring** (mostly configuration, since DeepAgents owns the loader):
  - Auto-pass `memory=["./PROJECT.md", "~/.quoriv/memory.md"]` to `create_deep_agent`
  - `/memory` slash command to view/edit
  - `quoriv init` command scaffolds a starter `PROJECT.md`
- **Per-task model routing**:
  - Default subagents (`researcher`, `debugger`, `reviewer`) each with their own `model=`
  - Configurable in TOML
- **Python plugin API**:
  - Plugins register tools via setuptools entry points (`quoriv.plugins`)
  - Loader merges them into `tools=`
- **MCP client**:
  - `quoriv.plugins.mcp` connects to MCP servers (stdio + SSE transports)
  - Server tools exposed via `tools=`
- **Cost dashboard**: `/cost` reads from `quoriv.observability.cost` (LangChain callbacks)
- **"Always allow" allowlist** (UX layer above `interrupt_on`): user can promote a one-time approval to permanent

**Deliverable:** feels personalized, extensible, cost-aware.

---

### Phase 3 — Multi-provider + polish (~2–3 weeks)
**Goal:** works with any model, polished for a public release.

- Providers: Anthropic, Gemini, Ollama, vLLM, OpenRouter (all via `quoriv.models.*`)
- Fallback chains (Anthropic → OpenAI → Ollama on transient failure)
- Web tools: `web_search`, `web_fetch`
- Hooks system: pre-tool / post-tool / on-message subscribers
- Replay mode: rerun a past session for debugging
- Themes (light / dark / custom)
- Cross-platform polish (Windows / macOS / Linux all tier-1)
- Eval harness on a small task set (regression catching)

**Deliverable:** public-ready feature set.

---

### Phase 4 — Release (~1–2 weeks)
**Goal:** real OSS launch.

- MkDocs documentation site
- PyPI publish (`pip install quoriv`)
- PyInstaller binaries for Windows / macOS / Linux
- CI matrix: tests on 3 OSes, release pipeline
- Security policy + responsible disclosure
- Telemetry opt-in (off by default)
- `v1.0.0` tag + announcement

**Deliverable:** publicly usable `v1.0.0` release.

---

## 8. The First Week — Day-by-Day (Phase 0)

| Day | Status | Work |
|---|---|---|
| **Day 1** | ✅ | Init repo, `pyproject.toml`, Apache 2.0, README, CONTRIBUTING, SECURITY, `.gitignore`, `.pre-commit-config.yaml`, CI |
| **Day 2** | ✅ | Folder skeleton (DeepAgents-revised), Pydantic v2 config schema, TOML loader, 36 tests |
| **Day 3** | ✅ | `keyring` keychain wrapper, model factory + OpenAI provider, 74 tests |
| **Day 4** | ⬜ | Minimal `cli.py` (Typer with `chat`, `config`, `doctor`) + `app.py` (Rich chat loop) streaming a direct OpenAI response. Still no DeepAgents wiring — just prove the UI loop works in isolation. |
| **Day 5** | ⬜ | Wire `create_deep_agent` with `LocalShellBackend`. **Full DeepAgents tool suite (write_todos, ls, read_file, write_file, edit_file, glob, grep, execute, task) available immediately.** End-to-end test: agent reads a file, edits it, runs tests. |
| **Weekend** | — | Catch-up, polish, write usage docs for what's there |

---

## 9. Slash Commands (planned set)

| Command | What it does |
|---|---|
| `/help` | List commands and usage |
| `/clear` | Clear the current conversation |
| `/model <name>` | Switch active model |
| `/mode <r/a/auto/yolo>` | Switch permission posture (translates to DeepAgents `permissions=` + `interrupt_on=`) |
| `/cost` | Show token usage and dollar cost |
| `/tools` | List enabled tools |
| `/save <name>` | Save current session (LangGraph checkpoint) |
| `/load <name>` | Resume a saved session |
| `/resume <id>` | Resume an interrupted session |
| `/memory` | View / edit `PROJECT.md` and `~/.quoriv/memory.md` |
| `/doctor` | Health check: API keys, model access, backend, tool config |

*Note: `/undo` is not in the v1 set — DeepAgents' `edit_file` does not have first-class undo. Phase 2+ if there's demand.*

---

## 10. Permission Modes — How They Compile to DeepAgents

Quoriv's 4 modes are a UX layer. They compile down to DeepAgents' two underlying mechanisms (`permissions=` rules and `interrupt_on=` dict).

| Mode | `permissions=` | `interrupt_on=` | Behavior |
|---|---|---|---|
| `read-only` | Path protection + deny-all-write rule (`["/**"]` write deny) | `{}` | Investigation only — writes blocked at tool level |
| `ask` | Path protection only | `{"write_file": True, "edit_file": True, "execute": True}` | Default — prompts before every write or shell |
| `auto` | Path protection only | `{"execute": True}` | Auto-runs writes; prompts for shell |
| `yolo` | Path protection only | `{}` | No prompts (path denylist still enforced) |

Path protection is the always-on layer:

```python
[
    FilesystemPermission(operations=["write"], paths=["/.env", "/.env.*"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/.git/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/.ssh/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/secrets/**"], mode="deny"),
]
```

These rules can never be removed via configuration — they are prepended to whatever the user's mode requires.

---

## 11. Configuration

### Global config: `~/.quoriv/config.toml`

```toml
[model]
default = "openai:gpt-4.1"
fast    = "openai:gpt-4o-mini"      # used for trivial / routing
strong  = "openai:gpt-4.1"          # used for hard reasoning

[permissions]
mode = "ask"

[ui]
theme = "dark"
```

### Project config: `.quoriv/config.toml` (in repo)

```toml
[model]
# project-level override
default = "anthropic:claude-sonnet-4-6"

[tools]
disabled = ["web_search"]            # if you want to lock down
```

API keys live in the OS keychain (via `keyring`), never on disk.

---

## 12. Memory System (delegated to DeepAgents)

DeepAgents' `MemoryMiddleware` loads markdown files at agent startup and injects them into the system prompt. Quoriv just points it at the right paths — no custom loader.

| Layer | Location | Owned by | Purpose |
|---|---|---|---|
| **Project memory** | `PROJECT.md` at repo root | User-edited markdown | Project facts (architecture, conventions, who-does-what) |
| **User memory** | `~/.quoriv/memory.md` | User-edited markdown | Personal preferences across all projects |
| **Session memory** | SQLite via `SqliteSaver` | LangGraph checkpointer | Full conversation history; resumable |
| **Working memory** | LangGraph state | DeepAgents | This-conversation context (auto-compacted by `SummarizationMiddleware`) |

Format for `PROJECT.md` and `memory.md`: free-form markdown (per Anthropic's AGENTS.md spec). No required structure.

---

## 13. Sources & Inspiration

- **[DeepAgents](https://github.com/langchain-ai/deepagents) 0.6.1** — the agent runtime. See [`docs/DEEPAGENTS_REFERENCE.md`](docs/DEEPAGENTS_REFERENCE.md) for the complete feature-by-feature breakdown of what we use.
- **[claw-code](https://github.com/ultraworkers/claw-code)** — Rust implementation of Claude Code-style harness. Reference for CLI UX patterns (sessions, `doctor` command, structure).
- **[awesome-cc-oss](https://github.com/rosaboyle/awesome-cc-oss)** — curated list of open-source Claude Code alternatives.
- **[Claude Code](https://www.anthropic.com/claude-code)** (Anthropic) — UX reference for terminal coding agents.
- **[Gemini CLI](https://github.com/google-gemini/gemini-cli)** (Google) — UX reference.
- **[Aider](https://aider.chat)** — patch-based editing patterns (not used directly — we use DeepAgents' `edit_file`).

---

## 14. Open Questions / TBD

- [x] ~~Final project name~~ → **Quoriv** (verified: PyPI free, npm free, GitHub `quoriv` free, no trademark, no AI-tool collision)
- [x] ~~GitHub home~~ → `github.com/BurhanHussain1/quoriv`
- [ ] Primary domain (`.dev` / `.sh` / `.ai`) — defer until v1.0 release
- [ ] Phase 3+: Which providers to add first after the OpenAI baseline (Anthropic recommended)
- [ ] Phase 4: Telemetry vendor (PostHog / Plausible / none)
- [ ] Add a Quoriv `regex_grep` tool? (DeepAgents' built-in `grep` is literal substring only)

---

## 15. Status

**Current phase:** Phase 0 ✅ complete (Days 1–5). Phase 1 in progress — Slice 1 (permission modes) ✅ complete.

**Test count:** 130 passing. All CI gates green: ruff, ruff format, mypy strict, pytest.

**Phase 0 deliverables:**
- Day 1 ✅ Repo scaffold + CI
- Day 2 ✅ Config layer + folder skeleton (Pydantic v2, TOML loader)
- Day 3 ✅ OS keychain + model factory + OpenAI provider
- Day 4 ✅ Typer CLI + Rich/prompt_toolkit chat loop (direct LLM streaming)
- Day 5 ✅ DeepAgents wired with `LocalShellBackend` (full built-in toolset live)

**Phase 1 progress (9 slices total):**
- Slice 1 ✅ Permission modes (4-mode → `interrupt_on=` translation, path-protection constants in canonical location)
- Slice 1b ⬜ Custom `wrap_tool_call` middleware enforcing `PATH_PROTECTION` against the live agent (DeepAgents 0.6.1 doesn't accept `permissions=` with sandbox backends)
- Slice 2 ⬜ Approval prompt UI for `interrupt_on` pauses
- Slice 3 ⬜ Markdown-aware streaming + diff renderer
- Slice 4 ⬜ Tree-sitter AST tools
- Slice 5 ⬜ Git tools
- Slice 6 ⬜ Language-aware test runner
- Slice 7 ⬜ `SqliteSaver` checkpointer for session persistence
- Slice 8 ⬜ Slash commands polish + status line
- Slice 9 ⬜ Trace log + integration tests

**Architecture revision (still applies):** Adopted DeepAgents-reuse model after auditing the installed 0.6.1 SDK. `src/quoriv/memory/` removed. `core/`, `tools/`, `permissions/`, `repo/` scopes narrowed (see folder tree above).

**Next action:** Phase 1 Slice 2 — approval prompt UI. With Slice 1 done, the agent already pauses before risky tools; Slice 2 renders the pause as a user-facing prompt (approve / deny, with auto-deny in `read-only` mode).
