# Quoriv

> An open-source, terminal-based AI coding agent. Model-agnostic. Locally-runnable. Fully extensible.

Quoriv is a Python-built coding agent that lives in your terminal and works directly inside your repository. It plans, reads and writes files, runs shell commands, executes tests, searches your codebase, and delegates work to specialized sub-agents — under a permission system you control. It is built on [DeepAgents](https://github.com/langchain-ai/deepagents) and [LangGraph](https://github.com/langchain-ai/langgraph), and works with OpenAI, Anthropic Claude, Google Gemini, Ollama (local), and self-hosted vLLM endpoints.

> **Status:** v1.0 released. `pip install quoriv` — see the [docs site](https://burhanhussain1.github.io/quoriv/) for usage.

---

## Why Quoriv

| Quality | What it means |
|---|---|
| **Model-agnostic** | One config flag swaps between OpenAI / Anthropic / Gemini / Ollama / vLLM. No vendor lock-in. |
| **Local-first option** | Run entirely offline with Ollama or a private vLLM server. Nothing leaves your machine. |
| **Repo-native** | Lives in your terminal, edits your real files, runs your real tests. No web upload, no copy-paste. |
| **Permission-aware** | Multi-tier modes (`read-only` / `ask` / `auto` / `yolo`) so you choose the autonomy level. |
| **Extensible** | Both [MCP](https://modelcontextprotocol.io) plugins (external) and a Python plugin API (internal). |
| **Memory** | Per-project + per-user + per-session memory. The agent remembers across runs. |
| **Cost-aware** | Per-task model routing: cheap fast model for trivial work, strong model for hard reasoning. |
| **Open-source** | Apache 2.0. Yours to read, modify, fork, and self-host. |

---

## Installation

> **Note:** Quoriv is not yet on PyPI. Once Phase 0 is complete, install with:

```bash
pip install quoriv
```

For development:

```bash
git clone https://github.com/BurhanHussain1/quoriv.git
cd quoriv
pip install -e ".[dev,ast]"
```

---

## Quick start

```bash
# Configure your API key (stored in OS keychain, never on disk)
quoriv config set openai

# Start a session in the current repo
quoriv chat

# Run with a specific permission mode
quoriv chat --mode read-only        # investigation only
quoriv chat --mode ask              # default — prompts before each risky tool
quoriv chat --mode auto             # auto-runs safe tools, prompts for risky ones
quoriv chat --mode yolo             # autonomous (use with care)

# Switch model
quoriv chat --model openai:gpt-4.1
quoriv chat --model anthropic:claude-sonnet-4-6
quoriv chat --model ollama:qwen2.5-coder:32b
```

---

## Configuration

Quoriv reads two TOML files (project config overrides global):

- **Global** — `~/.quoriv/config.toml`
- **Project** — `.quoriv/config.toml` in your repo

Example:

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
   models/  (OpenAI / Anthropic / Gemini / Ollama / vLLM)
        |
   tools/  +  permissions/  +  memory/  +  plugins/  +  repo/
```

See [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) for the full architecture and phase-by-phase roadmap.

---

## Built-in tools

| Category | Tools |
|---|---|
| Files | `read`, `write`, `edit`, `multi_edit`, `ls`, `glob`, `grep` |
| Shell | `execute` (with sandboxing + permission gating) |
| Code intel | `find_symbol`, `go_to_definition`, `find_references` (tree-sitter) |
| Git | `status`, `diff`, `log`, `commit`, `branch`, `blame` |
| Tests | `run_tests` (language-aware: pytest / jest / cargo / go test) |
| Web | `web_search`, `web_fetch` |
| Patch | `apply_diff` (safe unified-diff apply) |

Custom tools: write a Python plugin or connect any MCP server.

---

## Permission modes

| Mode | Read | Write | Shell | Use case |
|---|---|---|---|---|
| `read-only` | auto | blocked | blocked | Investigation, code review |
| `ask` | auto | prompt | prompt | Default — full control |
| `auto` | auto | auto-safe / prompt-risky | prompt-risky | Power-user productivity |
| `yolo` | auto | auto | auto | Trusted workflows only |

Path protection (e.g., `.env`, `~/.ssh`) is enforced in **every** mode.

---

## Slash commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/clear` | Clear the conversation |
| `/model <name>` | Switch active model |
| `/mode <mode>` | Switch permission posture |
| `/cost` | Show token usage and dollar cost |
| `/tools` | List enabled tools |
| `/undo` | Revert the last set of edits |
| `/save <name>` | Save current session |
| `/load <name>` | Resume a saved session |
| `/memory` | Inspect / edit memory |
| `/doctor` | Health check: API keys, model access, tool config |

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
| 0 | Foundation: scaffold, config, OpenAI provider | In progress |
| 1 | Core agent + tools + Rich TUI + permissions | Planned |
| 2 | Memory, model routing, MCP + Python plugins | Planned |
| 3 | Anthropic / Gemini / Ollama / vLLM, hooks, replay | Planned |
| 4 | OSS release: PyPI, binaries, docs site, v1.0.0 | Planned |

See [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) for the full plan.

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
