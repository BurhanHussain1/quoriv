# Quoriv

[![PyPI](https://img.shields.io/pypi/v/quoriv.svg)](https://pypi.org/project/quoriv/)
[![Python](https://img.shields.io/pypi/pyversions/quoriv.svg)](https://pypi.org/project/quoriv/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

> An open-source, terminal-based AI coding agent. Model-agnostic. Locally-runnable. Fully extensible.

Quoriv is a Python-built coding agent that lives in your terminal and works directly inside your repository. It plans, reads and writes files, runs shell commands, executes tests, searches your codebase, and delegates work to specialized sub-agents — under a permission system you control. It is built on [DeepAgents](https://github.com/langchain-ai/deepagents) and [LangGraph](https://github.com/langchain-ai/langgraph), and works with OpenAI, Anthropic Claude, Google Gemini, DeepSeek, Kimi, xAI Grok, OpenRouter, Ollama (local), and self-hosted vLLM endpoints.

> **Status:** stable and on PyPI — current release **v1.7.0**. `pip install quoriv`, then run `quoriv chat`. See the [docs site](https://burhanhussain1.github.io/quoriv/) for usage and the [changelog](CHANGELOG.md) for release history.

---

## Why Quoriv

| Quality | What it means |
|---|---|
| **Model-agnostic** | One config flag swaps between OpenAI / Anthropic / Gemini / DeepSeek / Kimi / Grok / OpenRouter / Ollama / vLLM. No vendor lock-in. |
| **Local-first option** | Run entirely offline with Ollama or a private vLLM server. Nothing leaves your machine. |
| **Repo-native** | Lives in your terminal, edits your real files, runs your real tests. No web upload, no copy-paste. |
| **Permission-aware** | Multi-tier modes (`read-only` / `ask` / `auto` / `yolo`) so you choose the autonomy level. |
| **Extensible** | Both [MCP](https://modelcontextprotocol.io) plugins (external) and a Python plugin API (internal). |
| **Memory** | Per-project + per-user + per-session memory. The agent remembers across runs. |
| **Cost-aware** | Per-task model routing plus token/dollar accounting via `/cost`. |
| **Open-source** | Apache 2.0. Yours to read, modify, fork, and self-host. |

---

## Installation

Requires Python 3.11 or newer.

```bash
pip install quoriv
```

Optional extras, installed on demand:

```bash
pip install "quoriv[all-providers]"   # Anthropic + Gemini + Ollama providers
pip install "quoriv[ast]"             # tree-sitter symbol intelligence (~80 languages)
pip install "quoriv[mcp]"             # MCP server support
pip install "quoriv[search]"          # Tavily-backed web_search
pip install "quoriv[all-providers,ast,mcp,search]"   # everything
```

Standalone binaries for Linux, macOS, and Windows are attached to each [GitHub release](https://github.com/BurhanHussain1/quoriv/releases) if you'd rather not install via pip.

For development:

```bash
git clone https://github.com/BurhanHussain1/quoriv.git
cd quoriv
pip install -e ".[dev,ast]"
```

---

## Quick start

```bash
# Start a session in the current repo. On first run, Quoriv walks you
# through provider + API key + model selection (keys go to the OS keychain).
quoriv chat

# Or configure a key up front
quoriv config set openai

# Run with a specific permission mode
quoriv chat --mode read-only        # investigation only
quoriv chat --mode ask              # default — prompts before each risky tool
quoriv chat --mode auto             # auto-runs safe tools, prompts for risky ones
quoriv chat --mode yolo             # autonomous (use with care)

# Switch model
quoriv chat --model openai:gpt-5.5
quoriv chat --model anthropic:claude-sonnet-4-6
quoriv chat --model ollama:qwen2.5-coder:32b
```

New to a codebase? Run `/init` inside a session — the agent explores the repo and writes a structured `PROJECT.md` that is auto-loaded into every future session.

---

## Configuration

Quoriv reads two TOML files (project config overrides global):

- **Global** — `~/.quoriv/config.toml`
- **Project** — `.quoriv/config.toml` in your repo

Example:

```toml
[model]
default = "openai:gpt-5.5"
fast    = "openai:gpt-5.4-mini"     # used for trivial / routing
strong  = "openai:gpt-5.5-pro"      # used for hard reasoning

[permissions]
mode = "ask"

[ui]
theme = "dark"

[subagents.researcher]
model = "fast"
```

See [`config.example.toml`](config.example.toml) for the annotated full surface, including `[cost.rates]`, `[plugins]`, and `[mcp.servers]`.

API keys live in the OS keychain via [`keyring`](https://pypi.org/project/keyring/) — never in plaintext.

---

## Architecture

```
Terminal (Rich + prompt_toolkit)
        |
   src/quoriv/cli.py
        |
   src/quoriv/app.py        <-- main loop
        |
   core/  (DeepAgents + LangGraph + routing + context)
        |
   models/  (OpenAI / Anthropic / Gemini / DeepSeek / Kimi / Grok / OpenRouter / Ollama / vLLM)
        |
   tools/  +  permissions/  +  memory/  +  plugins/  +  repo/
```

See [`PROJECT_PLAN.md`](PROJECT_PLAN.md) for the full architecture.

---

## Built-in tools

| Category | Tools |
|---|---|
| Files | `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`, `regex_grep` |
| Shell | `execute` (with permission gating) |
| Code intel | `find_symbol`, `go_to_definition`, `find_references` (stdlib `ast` for Python, tree-sitter for ~80 other languages) |
| Git (read) | `git_status`, `git_diff`, `git_log`, `git_blame` |
| Git (write) | `git_add`, `git_commit`, `git_stash` (HITL-gated) |
| Tests | `run_tests` (language-aware: pytest / jest / cargo / go test, with parsed pass/fail counts) |
| Web | `web_search`, `web_fetch` |
| Planning | `write_todos`, `task` (sub-agent delegation) |

Custom tools: write a Python plugin (`quoriv.plugins` entry point) or connect any MCP server.

---

## Permission modes

| Mode | Read | Write | Shell | Use case |
|---|---|---|---|---|
| `read-only` | auto | blocked | blocked | Investigation, code review |
| `ask` | auto | prompt | prompt | Default — full control |
| `auto` | auto | auto-safe / prompt-risky | prompt-risky | Power-user productivity |
| `yolo` | auto | auto | auto | Trusted workflows only |

Path protection (e.g., `.env`, `.git/`, `~/.ssh`, `secrets/`) is enforced in **every** mode. Approving a tool with "always" allowlists it for the rest of the session only.

---

## Slash commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/init` | Explore the repo and write / refresh `PROJECT.md` |
| `/clear` | Start a fresh conversation thread |
| `/login`, `/setup` | Provider + API key + model wizard |
| `/logout` | Remove the current provider's key from the keychain |
| `/mode <mode>` | Switch permission posture live |
| `/cost` | Token usage and estimated dollar cost |
| `/tools` | List enabled tools |
| `/memory` | Inspect memory files |
| `/save <name>` | Save the current session |
| `/load <name>` | Resume a saved session |
| `/resume` | Jump back to the most recently saved session |
| `/exit` | Leave the session |

CLI commands: `quoriv chat`, `quoriv init`, `quoriv doctor`, `quoriv version`, `quoriv config show|set|list-providers`.

---

## Development

```bash
# Set up
git clone https://github.com/BurhanHussain1/quoriv.git
cd quoriv
pip install -e ".[dev,ast]"
pre-commit install

# Run tests
pytest

# Lint + type-check
ruff check .
ruff format .
mypy

# Run the CLI from source
python -m quoriv chat
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contributor guidelines.

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundation: scaffold, config, OpenAI provider | Shipped |
| 1 | Core agent + tools + Rich TUI + permissions | Shipped |
| 2 | Memory, model routing, MCP + Python plugins | Shipped |
| 3 | Anthropic / Gemini / Ollama / vLLM, hooks, replay | Shipped |
| 4 | OSS release: PyPI, binaries, docs site, v1.0.0 | Shipped — v1.0.0, 2026-05-19 |
| 5 | Post-v1.0 UX polish: inline pickers, onboarding wizard, reasoning display, `/init` | Ongoing (v1.1 → v1.7) |

See [`PROJECT_PLAN.md`](PROJECT_PLAN.md) for the full plan and [`CHANGELOG.md`](CHANGELOG.md) for per-release detail.

---

## Inspiration

- [Claude Code](https://www.anthropic.com/claude-code) (Anthropic) — UX reference
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (Google) — UX reference
- [Aider](https://aider.chat) — patch-based editing patterns
- [DeepAgents](https://github.com/langchain-ai/deepagents) — agent runtime
- [claw-code](https://github.com/ultraworkers/claw-code) — Rust implementation reference

---

## License

[Apache 2.0](LICENSE) © 2026 Burhan Hussain
