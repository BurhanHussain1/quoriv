# `Quoriv` — Complete Project Plan

> Open-source, terminal-based AI coding agent. Built in Python on DeepAgents + LangGraph. Model-agnostic (OpenAI, Anthropic, Gemini, Ollama, vLLM). Inspired by Claude Code, Gemini CLI, and Aider — but locally-runnable, multi-provider, and fully extensible from day one.

---

## 1. Project Description

`Quoriv` is an open-source, terminal-based AI coding agent that helps developers understand, edit, debug, and ship code through natural-language conversation directly inside their repository. Built in Python on top of DeepAgents and LangGraph, it is model-agnostic by design — working with cloud APIs like OpenAI, Anthropic Claude, and Google Gemini, as well as fully private local models through Ollama and self-hosted vLLM endpoints — so users can choose between hosted intelligence and complete offline privacy.

The agent reads and writes files, runs shell commands, executes tests, searches and reasons about the codebase using grep and tree-sitter AST tools, plans multi-step work with a built-in to-do system, and delegates specialized subtasks to dedicated sub-agents, all under a multi-tier permission system. It supports MCP (Model Context Protocol) plugins and a native Python extension API for custom tools, maintains per-project and per-user memory files for persistent context across sessions, and uses per-task model routing to send trivial work to cheap fast models and hard reasoning to stronger ones.

---

## 2. Goals

### Primary goals
- Daily-driver coding assistant in any repository
- Open-source release under Apache 2.0
- Usable by individuals and small teams
- Works with both hosted APIs (OpenAI today, Anthropic / Gemini / OpenRouter / Together later) and local models (Ollama, vLLM)
- Extensible via MCP and a Python plugin API
- Persistent memory across sessions
- Safe by default through a multi-tier permission system

### Non-goals (for v1.0)
- VSCode/JetBrains extension (architecture supports it later, but not shipped in v1)
- Web UI (same — supported by architecture, not shipped)
- Built-in cloud / SaaS offering
- Fine-tuning or training models
- Mobile clients

---

## 3. Locked Design Decisions

| Area | Decision | Rationale |
|---|---|---|
| **Audience** | OSS release + team-usable | Apache 2.0 license is enterprise-friendly |
| **Architecture** | Monolithic Python CLI | Simpler; internal seams allow extracting a server later |
| **Agent model** | Single main agent + DeepAgents-style sub-agents on demand | Balanced cost vs capability |
| **Repo intel** | Grep + glob + read (Claude Code style) **plus** tree-sitter AST for symbol awareness | Best ratio of quality to effort; no embeddings/LSP for v1 |
| **Plugins** | Both MCP (external) + Python plugin API (internal) | Max flexibility, future-proof |
| **Sandbox** | No container; permission prompts + path protection | Simpler, faster, works on any OS |
| **Permission modes** | `read-only` / `ask` / `auto` / `yolo` — user-selectable per session | Multi-tier posture |
| **Model routing** | Per-task: small/cheap for trivial, large for hard | Cuts cost dramatically |
| **Providers (Phase 1)** | OpenAI | What the user has access to today |
| **Providers (Phase 3)** | Anthropic, Gemini, Ollama, vLLM, OpenRouter | Provider factory ready in Phase 1 |
| **TUI library** | `rich` (chat-scroll) + `prompt_toolkit` (input) | What Claude Code / Gemini CLI use |
| **CLI framework** | `typer` | Clean ergonomics, type-driven |
| **Memory** | Per-project + per-user + per-session, SQLite-backed | Industry-standard simple persistence |
| **Storage** | SQLite (sessions/memory/traces); TOML (config) | Single file, queryable, portable |
| **Distribution** | `pip install` first; PyInstaller binaries in Phase 4 | Lowest-friction path; binaries for non-Python users later |
| **Timeline** | 4 phases over ~3–4 months | "Build it right" pacing |
| **License** | Apache 2.0 | OSS-friendly + enterprise-compatible |

---

## 4. Tech Stack

### Runtime
- **Python 3.11+** (3.12 preferred — better asyncio + error messages)
- **`deepagents`** — the agent engine
- **`langgraph`** — included with deepagents
- **`langchain-openai`** — provider adapter (Phase 1)
- **`langchain-anthropic`** — provider adapter (Phase 3)
- **`langchain-google-genai`** — provider adapter (Phase 3)
- **`langchain-ollama`** — local model adapter (Phase 3)
- **`mcp`** — official MCP Python SDK (Phase 2)

### UI
- **`rich`** — markdown rendering, syntax highlighting, tables, diffs
- **`prompt_toolkit`** — multi-line input box at the bottom of the chat
- **`typer`** — CLI commands and flags

### Data
- **`pydantic`** v2 — config schemas + tool argument validation
- **`pydantic-settings`** — env var integration
- **`aiosqlite`** — async SQLite for sessions, memory, traces
- **`tomli` / built-in `tomllib`** — config file parsing
- **`keyring`** — OS keychain for API key storage

### Code understanding
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

```
quoriv/                              # repo root
├── pyproject.toml
├── README.md
├── LICENSE                                  # Apache-2.0
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── .pre-commit-config.yaml
├── .gitignore
├── .github/
│   ├── workflows/                           # CI: test, lint, release
│   │   ├── test.yml
│   │   ├── release.yml
│   │   └── lint.yml
│   └── ISSUE_TEMPLATE/
├── docs/                                    # MkDocs site (Phase 4)
│   ├── index.md
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
    ├── core/                                # AGENT CORE — separable from CLI
    │   ├── __init__.py
    │   ├── agent.py                         # DeepAgents wiring
    │   ├── runtime.py                       # the loop + streaming events
    │   ├── routing.py                       # per-task model routing
    │   ├── context.py                       # context compaction
    │   └── events.py                        # event bus -> CLI / future clients
    │
    ├── models/                              # Provider abstraction
    │   ├── __init__.py
    │   ├── base.py                          # Protocol + capability flags
    │   ├── factory.py                       # get_model("openai:gpt-4.1")
    │   ├── openai.py                        # Phase 1
    │   ├── anthropic.py                     # Phase 3
    │   ├── gemini.py                        # Phase 3
    │   ├── ollama.py                        # Phase 3
    │   ├── vllm.py                          # Phase 3
    │   └── openrouter.py                    # Phase 3
    │
    ├── tools/                               # Built-in tools
    │   ├── __init__.py
    │   ├── base.py                          # @tool decorator + permission wrap
    │   ├── files.py                         # read, write, edit, multi_edit, ls, glob
    │   ├── search.py                        # grep, file_glob
    │   ├── ast_tools.py                     # tree-sitter: find_symbol, go_to_def, refs
    │   ├── shell.py                         # execute, kill, background
    │   ├── git.py                           # status, diff, log, commit, blame
    │   ├── tests.py                         # language-aware test runner
    │   ├── web.py                           # search, fetch
    │   └── patch.py                         # safe unified-diff apply
    │
    ├── permissions/                         # The safety layer
    │   ├── __init__.py
    │   ├── modes.py                         # read-only / ask / auto / yolo
    │   ├── allowlist.py                     # remembered "always allow" patterns
    │   ├── guard.py                         # gatekeeper before any tool runs
    │   └── paths.py                         # path protection (.env, ~/.ssh, etc.)
    │
    ├── memory/
    │   ├── __init__.py
    │   ├── store.py                         # SQLite backbone
    │   ├── project.py                       # PROJECT.md auto-load
    │   ├── user.py                          # ~/.quoriv/memory.md
    │   └── session.py                       # checkpoint + resume
    │
    ├── plugins/
    │   ├── __init__.py
    │   ├── api.py                           # Python plugin API
    │   ├── loader.py                        # entry-points + dir discovery
    │   └── mcp/
    │       ├── __init__.py
    │       ├── client.py                    # MCP client over stdio/SSE
    │       └── registry.py                  # connected servers
    │
    ├── ui/                                  # All terminal rendering
    │   ├── __init__.py
    │   ├── chat.py                          # main scroll
    │   ├── stream.py                        # token streaming renderer
    │   ├── diff.py                          # diff display
    │   ├── prompts.py                       # approval prompts
    │   ├── slash.py                         # slash commands
    │   ├── status.py                        # status line (model, tokens, $, branch)
    │   └── theme.py                         # color themes
    │
    ├── config/
    │   ├── __init__.py
    │   ├── schema.py                        # Pydantic v2 settings
    │   ├── loader.py                        # merge global + project TOML
    │   └── keychain.py                      # OS keychain for API keys
    │
    ├── observability/
    │   ├── __init__.py
    │   ├── log.py                           # loguru
    │   ├── cost.py                          # per-call cost tracking
    │   ├── trace.py                         # local trace export (JSON)
    │   └── telemetry.py                     # opt-in only
    │
    └── repo/                                # Repo understanding
        ├── __init__.py
        ├── index.py                         # lazy file tree
        ├── ast.py                           # tree-sitter parsers per-language
        └── symbols.py                       # symbol lookup
```

**Why this shape:** the `core/` package can be imported and driven by any client — a CLI today, a VSCode extension server, a web UI later. The CLI is just one consumer.

---

## 6. Architecture (high-level)

```
                       Terminal (Rich + prompt_toolkit)
                                    |
                              src/<name>/cli.py
                                    |
                              src/<name>/app.py        <-- main loop
                                    |
       +----------------------------+----------------------------+
       |                            |                            |
   ui/ (rendering)         core/ (agent runtime)         observability/
                                    |
                          +---------+---------+
                          |                   |
                    DeepAgents +         Model factory
                    LangGraph                 |
                          |             OpenAI / Anthropic /
                          |             Gemini / Ollama / vLLM
                          |
              +-----------+------------+
              |           |            |
          tools/    permissions/    memory/
                        |
                +-------+--------+
                |                |
           plugins/ (MCP +   repo/ (tree-sitter,
           Python API)        grep, index)
```

---

## 7. Phased Build Plan (~3–4 months)

### Phase 0 — Foundation (~1 week)
**Goal:** the skeleton is ready, a "hello world" agent runs.

- Repo init, `pyproject.toml`, `ruff`, `mypy`, `pytest`, `pre-commit`
- Apache 2.0 license, README, CONTRIBUTING, SECURITY
- Folder skeleton (all stub files)
- Config system: load global + project TOML
- API key via `keyring`
- OpenAI provider wired through the model factory
- Smoke test: agent answers "hello"

**Deliverable:** `quoriv chat` opens a terminal, you type, model responds. No tools yet.

---

### Phase 1 — Core Agent + CLI (~3–4 weeks)
**Goal:** a usable Claude-Code-like CLI for real work.

- DeepAgents integration with custom tool injection
- Built-in tools (permission-wrapped):
  - `read`, `write`, `edit`, `multi_edit`, `ls`, `glob`, `grep`, `execute`
- Tree-sitter AST tools:
  - `find_symbol`, `go_to_definition`, `find_references`
- Permission system:
  - All four modes (`read-only` / `ask` / `auto` / `yolo`)
  - `--mode` CLI flag
  - Per-session "always allow" allowlist
- Path protection (block `.env`, `~/.ssh`, system paths by default)
- Rich TUI:
  - Streaming markdown
  - Syntax-highlighted code blocks
  - Inline/side-by-side diff rendering
  - Approval prompts with arrow-key navigation
- Slash commands: `/help` `/clear` `/model` `/cost` `/tools` `/mode` `/undo` `/save` `/load` `/doctor`
- Status line: model, tokens used, cost, git branch
- Session save/load to SQLite
- Local trace log
- Tests: unit per tool, integration for the loop

**Deliverable:** usable daily for real coding tasks.

---

### Phase 2 — Memory, Routing, Plugins (~3–4 weeks)
**Goal:** the agent feels intelligent across sessions and is extensible.

- Project memory: auto-load `PROJECT.md` from working dir
- User memory: `~/.quoriv/memory.md` + structured facts in SQLite
- Session checkpoint + resume (`/resume <id>`)
- Context compaction: summarize old turns when window fills
- Per-task model routing: classifier picks small vs large model
- Python plugin API: third-party packages register tools via entry points
- MCP client: connect to external MCP servers (GitHub, Slack, DBs, etc.)
- Sub-agent system polish: expose researcher / debugger / reviewer agents
- Cost dashboard: `/cost` shows per-session and per-day breakdown

**Deliverable:** feels personalized and extensible.

---

### Phase 3 — Multi-Provider + Polish (~2–3 weeks)
**Goal:** works with any model, polished for a public release.

- Providers: Anthropic, Gemini, Ollama, vLLM, OpenRouter
- Fallback chains (Anthropic → OpenAI → Ollama on failure)
- Web tools: `web_search`, `web_fetch`
- Git tools: full set (`status`, `diff`, `log`, `commit`, `branch`, `blame`)
- Test runner: language detection + `pytest` / `jest` / `cargo test` / `go test`
- Hooks system: `pre_tool`, `post_tool`, `on_message`
- Replay mode: re-run a past session for debugging
- Themes (light / dark / custom)
- Cross-platform polish (Windows, macOS, Linux all tier-1)
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

| Day | Work |
|---|---|
| **Day 1** | Init repo. `pyproject.toml` with deps. Apache 2.0 license. README skeleton. `.gitignore`, `.pre-commit-config.yaml`. Basic CI workflow (lint + test on Python 3.11/3.12). |
| **Day 2** | Folder skeleton (every stub file). Pydantic v2 config schema. TOML loader (global `~/.quoriv/config.toml` + project `.quoriv/config.toml`). |
| **Day 3** | `keyring` integration for the OpenAI key. Model factory with one provider (OpenAI) wired through. |
| **Day 4** | Minimal `cli.py` (Typer) + `app.py` (Rich chat loop) that streams a response from OpenAI. No tools, no DeepAgents yet. |
| **Day 5** | Add DeepAgents with one tool (`read_file`). End-to-end loop confirmed: agent reads a file and answers about it. |
| **Weekend** | Catch-up, polish, write README sections for what's there. |

---

## 9. Slash Commands (planned set)

| Command | What it does |
|---|---|
| `/help` | List commands and usage |
| `/clear` | Clear the current conversation |
| `/model <name>` | Switch active model |
| `/mode <r/a/auto/yolo>` | Switch permission posture |
| `/cost` | Show token usage and dollar cost |
| `/tools` | List enabled tools |
| `/undo` | Revert the last set of edits |
| `/save <name>` | Save current session |
| `/load <name>` | Resume a saved session |
| `/resume <id>` | Resume an interrupted session |
| `/memory` | Inspect / edit project + user memory |
| `/doctor` | Health check: API keys, model access, tool config |

---

## 10. Permission Modes

| Mode | Read | Write | Shell | Behavior |
|---|---|---|---|---|
| `read-only` | auto | blocked | blocked | Investigation only |
| `ask` | auto | prompt | prompt | Default for new sessions |
| `auto` | auto | auto-safe / prompt-risky | prompt-risky | Power-user default |
| `yolo` | auto | auto | auto | Trusted workflows only |

Path protection (e.g., `.env`, `~/.ssh`) is enforced in **every** mode, including `yolo`.

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

## 12. Memory System

| Layer | Location | Purpose |
|---|---|---|
| **Project memory** | `PROJECT.md` at repo root | Project-specific facts the agent should know (architecture, conventions, who-does-what) |
| **User memory** | `~/.quoriv/memory.md` + SQLite | Personal preferences and patterns across all projects |
| **Session memory** | SQLite | Full conversation history; resumable |
| **Working memory** | LangGraph state | This-conversation context |

---

## 13. Sources & Inspiration

- **DeepAgents** — `langchain-ai/deepagents` — the agent engine (planning, sub-agents, filesystem tools, shell, context summarization). Provides ~80% of the agent runtime out of the box.
- **claw-code** — `ultraworkers/claw-code` — Rust implementation of Claude Code-style harness. Reference for CLI UX patterns (sessions, `doctor` command, structure).
- **awesome-cc-oss** — `rosaboyle/awesome-cc-oss` — curated list of open-source Claude Code alternatives.
- **Claude Code** (Anthropic) — UX reference for terminal coding agents.
- **Gemini CLI** (Google) — UX reference.
- **Aider** — patch-based editing patterns.

---

## 14. Open Questions / TBD

- [x] ~~Final project name~~ → **Quoriv** (verified: PyPI free, npm free, GitHub `quoriv` free, no trademark, no AI-tool collision)
- [ ] GitHub username / organization
- [ ] Primary domain (`.dev` / `.sh` / `.ai`)
- [ ] Phase 3+: Which providers to add first after the OpenAI baseline (Anthropic recommended)
- [ ] Phase 4: Telemetry vendor (PostHog / Plausible / none)

---

## 15. Status

**Current phase:** Pre-Phase-0 → Phase 0 (name locked: **Quoriv**; awaiting GitHub handle to begin scaffolding).

**Next action:** confirm GitHub handle/org, then start Phase 0 Day 1 (repo init).
