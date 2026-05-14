# DeepAgents Reference (internal)

> Working reference for the **DeepAgents 0.6.1** SDK Quoriv is built on.
> Source: `.venv/Lib/site-packages/deepagents/`
> Read this before building anything that might overlap with the SDK — most of what looks like "agent infrastructure" is already provided.

---

## TL;DR — what DeepAgents gives you for free

| Feature | Built-in? | Mechanism |
|---|---|---|
| Planning / todo list | ✅ | `TodoListMiddleware` → `write_todos` tool |
| File ops (read/write/edit/ls/glob/grep) | ✅ | `FilesystemMiddleware` |
| Shell execute | ✅ | `SandboxBackendProtocol.execute` (when backend supports it) |
| Sub-agents (sync + remote/async) | ✅ | `SubAgentMiddleware`, `AsyncSubAgentMiddleware` → `task` tool |
| Auto general-purpose subagent | ✅ | Inserted automatically unless overridden |
| Context compaction | ✅ | `SummarizationMiddleware` (token-aware) |
| Human-in-the-loop / approval | ✅ | `HumanInTheLoopMiddleware` via `interrupt_on={...}` |
| Filesystem permissions (allow/deny rules) | ✅ | `FilesystemPermission` evaluated by `FilesystemMiddleware` |
| Persistent project/user memory | ✅ | `MemoryMiddleware` (AGENTS.md spec) |
| Anthropic-style skills | ✅ | `SkillsMiddleware` (SKILL.md with YAML frontmatter) |
| Anthropic prompt caching | ✅ | `AnthropicPromptCachingMiddleware` (always on; no-ops elsewhere) |
| Multi-provider model resolution | ✅ | `init_chat_model(...)` + `ProviderProfile` |
| Per-model harness tuning | ✅ | `HarnessProfile` |
| Streaming | ✅ | Compiled LangGraph graph |
| Checkpointing / session persistence | ✅ | Pass `checkpointer=` (any LangGraph `Checkpointer`) |
| Structured output | ✅ | `response_format=` |

**Quoriv adds:** CLI/TUI, config layer, OS keychain, multi-tier permission UX, AST tools, git tools, web tools, MCP client, cost tracking, our Phase-3 providers, and the Rich-based renderers. Nothing more agent-runtime-y than that.

---

## Public API surface

```python
from deepagents import (
    create_deep_agent,            # main entry point
    SubAgent,                     # TypedDict spec for a sync subagent
    CompiledSubAgent,             # TypedDict wrapping a pre-built runnable
    AsyncSubAgent,                # TypedDict for remote/async subagent
    SubAgentMiddleware,
    AsyncSubAgentMiddleware,
    SubagentTransformer,
    SubagentRunStream,
    AsyncSubagentRunStream,
    FilesystemMiddleware,
    FilesystemPermission,
    MemoryMiddleware,
    HarnessProfile,
    HarnessProfileConfig,
    GeneralPurposeSubagentProfile,
    ProviderProfile,
    register_harness_profile,
    register_provider_profile,
    __version__,                  # currently "0.6.1"
)
```

Also useful (not in top-level `__all__` but stable):

```python
from deepagents.backends import (
    BackendProtocol,
    StateBackend,                 # default — files in LangGraph state (ephemeral)
    FilesystemBackend,            # real disk (no sandbox)
    LocalShellBackend,            # real disk + real shell (FilesystemBackend + SandboxBackendProtocol)
    StoreBackend,                 # LangGraph BaseStore
    LangSmithSandbox,             # remote sandbox via LangSmith
    ContextHubBackend,            # LangChain context hub
    CompositeBackend,             # combine multiple
    BackendContext,
    NamespaceFactory,
    DEFAULT_EXECUTE_TIMEOUT,      # 120s
)
from deepagents.middleware import (
    SkillsMiddleware,
    SummarizationMiddleware,
    SummarizationToolMiddleware,
    create_summarization_tool_middleware,
)
```

---

## `create_deep_agent` — the entry point

```python
create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: Sequence[SubAgent | CompiledSubAgent | AsyncSubAgent] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    permissions: list[FilesystemPermission] | None = None,
    backend: BackendProtocol | BackendFactory | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    response_format: ResponseFormat[ResponseT] | type[ResponseT] | dict[str, Any] | None = None,
    context_schema: type[ContextT] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph
```

Returns a compiled LangGraph graph with:
- `recursion_limit=9999` (effectively unbounded loops by default)
- Metadata: `ls_integration="deepagents"`, version tag, optional `lc_agent_name`

### Key parameters in plain language

| Param | What it does | Quoriv mapping |
|---|---|---|
| `model` | `"provider:name"` string OR pre-built `BaseChatModel`. **`None` is deprecated** (will be removed in 1.0.0) — always pass explicitly. | Use our `quoriv.models.get_model()` to build the BaseChatModel, then pass instance. |
| `tools` | *Additional* tools merged with the built-ins. Additive only — to drop a built-in, use `HarnessProfile.excluded_tools`. | Pass our AST/git/web/MCP tools here. |
| `system_prompt` | User prefix; sits at the front of the final prompt. Can be `SystemMessage` to preserve Anthropic cache_control markers. | Empty for v1; later we can pass project-specific guidance. |
| `middleware` | Extra middleware inserted between the base stack and the tail stack. | Mostly leave empty; we add custom only if we need cross-call interception. |
| `subagents` | Specs for delegated workers. Three types (see below). | Define researcher/debugger/reviewer subagents in Phase 2. |
| `skills` | Paths to skill directories (POSIX, relative to backend root). | Could map to project `.quoriv/skills/` + user `~/.quoriv/skills/`. |
| `memory` | Paths to AGENTS.md files. Loaded at startup, injected into system prompt. | Map our `PROJECT.md` + `~/.quoriv/memory.md` here. |
| `permissions` | List of `FilesystemPermission` rules for the main agent (subagents inherit unless overridden). | Translate our `read-only/ask/auto/yolo` mode into this list. |
| `backend` | File storage + (optional) execution. Default is `StateBackend()`. | For Quoriv we want `LocalShellBackend(root_dir=cwd)` so reads/writes/shell hit the real repo. |
| `interrupt_on` | `{"edit_file": True, ...}` — pause for approval before listed tools. | Map our `ask`/`auto` modes to this dict. |
| `response_format` | Pydantic/TypedDict for structured output. | Not used in v1. |
| `checkpointer` | Persist conversation state across runs. | Use `langgraph.checkpoint.sqlite.SqliteSaver` pointed at our session DB. |
| `store` | Optional persistent KV store (required if backend is `StoreBackend`). | Not used unless we choose StoreBackend. |

### Always-on middleware stack (in order)

```
TodoListMiddleware
SkillsMiddleware            (if skills=)
FilesystemMiddleware        ← REQUIRED scaffolding; cannot be excluded
SubAgentMiddleware          ← REQUIRED scaffolding; cannot be excluded (when subagents exist)
AsyncSubAgentMiddleware     (if any AsyncSubAgent in subagents=)
SummarizationMiddleware
PatchToolCallsMiddleware

  ─── user middleware= inserted here ───

(HarnessProfile.extra_middleware)
_ToolExclusionMiddleware    (if profile has excluded_tools)
AnthropicPromptCachingMiddleware    ← unconditional; no-ops for non-Anthropic
MemoryMiddleware            (if memory=)
HumanInTheLoopMiddleware    (if interrupt_on=)
```

Two are *required scaffolding* — `FilesystemMiddleware` and `SubAgentMiddleware`. Excluding them via `HarnessProfile.excluded_middleware` raises `ValueError`.

---

## Built-in tools

Always present (unless filtered by `HarnessProfile.excluded_tools`):

| Tool | Source | Notes |
|---|---|---|
| `write_todos` | `TodoListMiddleware` | LangChain SDK's built-in; manages a markdown-style todo list. |
| `ls` | `FilesystemMiddleware` | Lists files; returns `FileInfo` dicts with path, is_dir, size, modified_at. |
| `read_file` | `FilesystemMiddleware` | `cat -n` style output; default 2000-line limit; supports `offset`/`limit`. |
| `write_file` | `FilesystemMiddleware` | Errors if file exists. |
| `edit_file` | `FilesystemMiddleware` | Exact string replacement; `replace_all` flag; `old_string` must be unique unless replace_all. |
| `glob` | `FilesystemMiddleware` | wcmatch globs with `**`, `*`, `?`, `[abc]`. POSIX paths. |
| `grep` | `FilesystemMiddleware` | **Literal substring match (NOT regex)**. Optional path + glob filters. Returns `GrepMatch` (path, line, text). |
| `execute` | `FilesystemMiddleware` (delegates to `SandboxBackendProtocol.execute`) | Only registered if the backend implements `SandboxBackendProtocol`. Returns `ExecuteResponse(output, exit_code, truncated)`. |
| `task` | `SubAgentMiddleware` | Only registered if at least one synchronous subagent exists (the default `general-purpose` counts). |

**Important nuance:** `grep` is literal substring, not regex. If we want regex search we add our own tool.

### How tools see the filesystem

All built-in file tools talk to a **`BackendProtocol`**, not to disk directly. The backend decides where bytes actually live (state, real disk, sandbox, remote, etc.). Custom Quoriv tools can use the same backend by calling `runtime.context_state.backend` (via `ToolRuntime`) for consistency, or hit disk directly if we don't care.

---

## Backends (file storage + optional execution)

| Backend | Storage | `execute()`? | When to use |
|---|---|---|---|
| `StateBackend` (default) | LangGraph state — ephemeral within thread, persists via checkpointer. | ❌ | Demos, tests, anywhere disk shouldn't be touched. |
| `FilesystemBackend` | Real disk under `root_dir`. | ❌ | Local coding tools that want disk reads but no shell. |
| `LocalShellBackend` | Real disk + real shell. **No sandbox.** | ✅ | **What Quoriv uses.** Local dev CLIs. |
| `StoreBackend` | LangGraph `BaseStore` (Postgres, Redis, etc.). | ❌ | Web/server deployments wanting persistent files. |
| `LangSmithSandbox` | Remote sandbox over LangSmith. | ✅ | Cloud sandbox execution. |
| `ContextHubBackend` | LangChain context hub. | ❌ | Hosted file context. |
| `CompositeBackend` | Combines multiple backends with path-based routing. | depends on parts | Layer real disk + state, etc. |

`SandboxBackendProtocol` extends `BackendProtocol` with:
- `id: str` — unique identifier
- `execute(command, *, timeout=None) -> ExecuteResponse`
- `aexecute(command, *, timeout=None) -> ExecuteResponse`

`execute()` returns:
```python
@dataclass
class ExecuteResponse:
    output: str            # combined stdout + stderr
    exit_code: int | None  # None if unknown
    truncated: bool        # backend-side truncation flag
```

`DEFAULT_EXECUTE_TIMEOUT = 120` seconds.

### Quoriv choice: `LocalShellBackend(root_dir=<cwd>)`

For Quoriv's "live in your terminal, edit your real files" UX, `LocalShellBackend` is the right default. It gives us:
- Real file reads/writes/edits on disk
- Real shell `execute` for tests, git, builds
- HITL gating via our permission modes

Security risks (per DeepAgents docs) are exactly the ones we already plan to mitigate: HITL approval, path protection (`.env`, `~/.ssh`), command allowlists.

---

## Middleware (composable features)

DeepAgents differentiates two tool paths:

1. **SDK middleware** — intercepts every LLM request via `wrap_model_call()`. Can inject tools, modify system prompt per-call, filter tools dynamically, track cross-turn state.
2. **Plain tools** (in `tools=[]`) — stateless functions the LLM can call. No interception.

Use middleware when you need:
- Modify system prompt or tool list per call
- Cross-turn state
- Dynamic tool filtering

Use plain tools when:
- Function is stateless
- No per-call modification needed
- Tool is consumer-specific

### Built-in middleware

| Middleware | Effect | Where it lives |
|---|---|---|
| `TodoListMiddleware` | Adds `write_todos` tool; tracks a todo list across turns. | `langchain.agents.middleware` |
| `SkillsMiddleware` | Loads `SKILL.md` files; injects skill instructions into system prompt; exposes any `allowed_tools` declared per skill. | `deepagents.middleware.skills` |
| `FilesystemMiddleware` | Adds `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep`/`execute` tools; enforces `FilesystemPermission` rules. | `deepagents.middleware.filesystem` |
| `SubAgentMiddleware` | Adds `task` tool; manages declarative `SubAgent` specs. | `deepagents.middleware.subagents` |
| `AsyncSubAgentMiddleware` | Adds async-subagent tools (`launch_task`, `check_task`, `update_task`, `cancel_task`, `list_tasks`) for remote/long-running subagents. | `deepagents.middleware.async_subagents` |
| `SummarizationMiddleware` | Counts tokens; truncates old tool calls; replaces history with summaries when window fills. Model-aware. | `langchain.agents.middleware` (created via `create_summarization_middleware(model, backend)`) |
| `PatchToolCallsMiddleware` | Patches malformed tool calls before they reach the runtime. | `deepagents.middleware.patch_tool_calls` |
| `MemoryMiddleware` | Loads AGENTS.md files; injects into system prompt; optional Anthropic cache_control. | `deepagents.middleware.memory` |
| `HumanInTheLoopMiddleware` | Pauses before listed tools per `interrupt_on=` config. Requires a checkpointer. | `langchain.agents.middleware` |
| `AnthropicPromptCachingMiddleware` | Marks cache breakpoints on Anthropic models; no-ops for others. | `langchain_anthropic.middleware` |
| `_ToolExclusionMiddleware` | Filters tools listed in `HarnessProfile.excluded_tools`. Private. | `deepagents.middleware._tool_exclusion` |

### Writing custom middleware

Subclass `AgentMiddleware` from `langchain.agents.middleware.types`. Override:
- `wrap_model_call(request, handler)` — intercept every LLM request
- `on_message(message, state)` — observe new messages
- Define a typed `State` for cross-turn persistence

Custom middleware is **rarely needed for Quoriv** — almost everything we want hangs off `tools=`, `interrupt_on=`, `permissions=`, or `memory=`.

---

## Subagents

Three flavors, distinguished by the keys they declare:

### 1. `SubAgent` — declarative synchronous

```python
SubAgent = TypedDict(
    "SubAgent",
    {
        "name": str,                  # required, used as the task() target
        "description": str,           # required, helps main agent route
        "system_prompt": str,         # required
        "tools": NotRequired[...],    # inherits main agent's tools if omitted
        "model": NotRequired[str | BaseChatModel],
        "middleware": NotRequired[list[AgentMiddleware]],
        "interrupt_on": NotRequired[dict[str, bool | InterruptOnConfig]],
        "skills": NotRequired[list[str]],
        "permissions": NotRequired[list[FilesystemPermission]],
        "response_format": NotRequired[...],
    },
)
```

Invoked through the `task` tool. Subagents get the full base middleware stack auto-applied (TodoList, Filesystem, Summarization, PatchToolCalls, etc.) before any `middleware` you specify.

### 2. `CompiledSubAgent` — pre-built runnable

```python
CompiledSubAgent = TypedDict("CompiledSubAgent", {
    "name": str,
    "description": str,
    "runnable": Runnable,             # a pre-compiled LangGraph runnable
})
```

The runnable's state schema must include `messages`. The final message becomes the `ToolMessage` content returned to the parent.

### 3. `AsyncSubAgent` — remote/background

```python
AsyncSubAgent = TypedDict("AsyncSubAgent", {
    "name": str,
    "description": str,
    "graph_id": str,                  # identifies remote graph (e.g., LangSmith deployment)
    "url": NotRequired[str],
    "headers": NotRequired[dict[str, str]],
})
```

Routed to `AsyncSubAgentMiddleware`. Exposes async tools (`launch_task`, `check_task`, etc.) instead of a single `task` call. Useful for long-running background work.

### Auto general-purpose subagent

Unless you provide a subagent named `general-purpose` (or the active `HarnessProfile.general_purpose_subagent.enabled = False`), DeepAgents auto-adds one with:

- name: `"general-purpose"`
- model: same as main agent
- tools: inherits main agent's tools
- All base middleware applied

To run **without the `task` tool**, set `general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)` on a registered profile AND pass no synchronous subagents.

### Permission inheritance

Subagent permissions resolution:
1. If `SubAgent["permissions"]` set → use it, **replacing** parent rules entirely.
2. Else → inherit `create_deep_agent(permissions=...)` from main agent.

Same logic applies to `interrupt_on` (declarative SubAgent inherits; CompiledSubAgent and AsyncSubAgent do **not** inherit).

---

## Profiles

Two registries, both **beta** APIs:

### `ProviderProfile` — model construction

Controls what `init_chat_model` does. Built-in profiles:
- **OpenAI** — defaults to Responses API; honors `OPENAI_API_KEY`.
- **OpenRouter** — adds app attribution headers.

Register with `register_provider_profile()`.

### `HarnessProfile` — agent shaping

Controls what `create_deep_agent` does *after* the model exists. Built-in profiles for:
- `claude-sonnet-4-6`
- `claude-opus-4-7`
- `claude-haiku-4-5`
- OpenAI Codex models

```python
HarnessProfile(
    base_system_prompt: str | None = None,        # replaces BASE if set
    system_prompt_suffix: str | None = None,      # always appended last
    excluded_tools: set[str] | None = None,       # filter by tool name
    excluded_middleware: list[type | str] = []    # filter by class or .name (NOT scaffolding)
    extra_middleware: Sequence[AgentMiddleware | Callable[[ModelRequest], AgentMiddleware]] = (),
    tool_description_overrides: dict[str, str] = {},  # rewrite tool descriptions
    general_purpose_subagent: GeneralPurposeSubagentProfile | None = None,
)
```

Register with `register_harness_profile()`. Additive merge — re-registering under an existing key layers on top.

---

## Permission system — `FilesystemPermission`

```python
@dataclass
class FilesystemPermission:
    operations: list[FilesystemOperation]   # ["read"] | ["write"] | ["read", "write"]
    paths: list[str]                        # wcmatch globs; MUST start with "/"; no ".." or "~"
    mode: Literal["allow", "deny"] = "allow"
```

Where `FilesystemOperation = Literal["read", "write"]`.

### Built-in tool → operation mapping
```python
{
    "ls":         "read",
    "read_file":  "read",
    "glob":       "read",
    "grep":       "read",
    "write_file": "write",
    "edit_file":  "write",
}
```

### Evaluation
- Rules evaluated **in declaration order**; first match wins.
- If no rule matches → call is **allowed**.
- `execute` is **not** gated by this system — gate it separately via `interrupt_on` or by choosing the backend.

### Example
```python
permissions = [
    FilesystemPermission(operations=["write"], paths=["/.env", "/.env.*"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/.git/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/secrets/**"], mode="deny"),
]
```

---

## Human-in-the-Loop — `interrupt_on`

```python
interrupt_on = {
    "edit_file": True,                          # boolean = simple pause
    "write_file": True,
    "execute": InterruptOnConfig(
        # full config for richer prompts; see langchain.agents.middleware
    ),
}
```

Pauses agent execution at the listed tool calls, surfacing the call to a checkpointed thread for user approval. **Requires a `checkpointer=`.**

Inheritance:
- Declarative `SubAgent` inherits parent's `interrupt_on` unless it sets its own.
- `CompiledSubAgent` does **not** inherit.
- `AsyncSubAgent` does **not** inherit.

### Quoriv mapping of permission modes

| Mode | `permissions` | `interrupt_on` |
|---|---|---|
| `read-only` | Deny all write paths (`["/**"]` write) | (irrelevant — writes are blocked) |
| `ask` | Path protection only (`.env`, `.git`, etc.) | `{"write_file": True, "edit_file": True, "execute": True}` |
| `auto` | Path protection | `{"execute": True}` (auto-approve writes, prompt for shell) |
| `yolo` | Path protection (still enforce critical denylist) | `{}` (no prompts) |

---

## Memory (AGENTS.md)

`memory=` parameter takes paths to markdown files. Format: free-form markdown — no required structure. Loaded once at agent startup, concatenated in order (later sources after earlier), injected into the system prompt under `<agent_memory>...</agent_memory>`.

Conventional sources (per Anthropic's AGENTS.md spec):
```python
memory=[
    "~/.quoriv/AGENTS.md",       # or PROJECT.md / memory.md — naming is free
    "./.quoriv/AGENTS.md",
]
```

State key: `memory_contents: dict[path → content]` (private state attribute, not exposed in final state).

Anthropic prompt caching: `MemoryMiddleware` automatically applies `cache_control` breakpoints when an Anthropic model is in use. Safe to enable unconditionally.

---

## Skills (SKILL.md)

`skills=` parameter takes paths to **skill source directories** (not individual files). Each skill is a directory containing `SKILL.md` with YAML frontmatter:

```
/skills/user/web-research/
├── SKILL.md          # required
└── helper.py         # optional supporting files
```

```markdown
---
name: web-research
description: Structured approach to conducting thorough web research
license: MIT
allowed_tools: [web_search, web_fetch]
---

# Web Research Skill

## When to Use
- User asks you to research a topic
...
```

Sources are scanned in order; **last wins** on name collisions (so layering goes: built-in → user → project → team).

Special source labeling:
- Bare path: label = `Path(source).name.capitalize()`
- Special case: leaf `skills` climbs one level (`~/.claude/skills` → `Claude`, not `Skills`)
- Special case: leaf `built_in_skills` → `Built-in`
- Pass `(path, label)` tuple to disambiguate manually

### Skills vs. Memory

| | Skills | Memory |
|---|---|---|
| Loaded into prompt | Lazily (progressive disclosure) | Always, in full |
| Format | SKILL.md with YAML frontmatter | Plain markdown (free-form) |
| Granularity | Named, discoverable | Just dumped in |
| Use case | Optional workflows ("how to do X") | Project facts & conventions |

---

## Prompt assembly

Final system prompt = up to four named parts, in this order:

```
USER  →  (BASE | CUSTOM)  →  SUFFIX
```

| Part | Source |
|---|---|
| `USER` | `create_deep_agent(system_prompt=...)`. Always at the front, so caller instructions take precedence. |
| `BASE` | The hardcoded `BASE_AGENT_PROMPT` constant. Used when no profile sets `base_system_prompt`. |
| `CUSTOM` | `HarnessProfile.base_system_prompt`. When set, **replaces** `BASE` entirely. |
| `SUFFIX` | `HarnessProfile.system_prompt_suffix`. Always last, so model-tuning sits closest to the conversation. |

Joined by blank lines (`\n\n`).

Passing `system_prompt` as a `SystemMessage` preserves `cache_control` markers and appends right-hand content as an extra text block.

The default `BASE_AGENT_PROMPT` is opinionated:
- Be concise
- No preamble ("Sure!", "I'll now...")
- Understand → act → verify cycle
- Don't ask for details already supplied
- Brief progress updates for long tasks

For Quoriv we can pass our own `system_prompt` to layer project conventions on top, but probably leave the BASE alone unless we have a strong reason.

---

## State & checkpointing

DeepAgents uses a custom `_DeepAgentState` extending `AgentState` with a `DeltaChannel` on `messages` (snapshots every 50 messages). This keeps checkpoint storage at O(N) instead of O(N²) for long sessions.

Pass any LangGraph `Checkpointer` to enable resumability:

```python
from langgraph.checkpoint.sqlite import SqliteSaver

with SqliteSaver.from_conn_string("./.quoriv/sessions.db") as saver:
    agent = create_deep_agent(model=..., checkpointer=saver)
    result = agent.invoke({"messages": [...]}, config={"configurable": {"thread_id": "session-42"}})
```

**Required for**: `interrupt_on=` (HITL), session resume.

---

## Model resolution

```python
from deepagents._models import resolve_model
```

- If `model` is a `BaseChatModel` → returned as-is.
- If `model` is a string → `init_chat_model(spec, **apply_provider_profile(spec))`.
- `init_chat_model` understands `"provider:model"` (e.g., `"openai:gpt-4.1"`, `"anthropic:claude-sonnet-4-6"`, `"ollama:qwen2.5-coder:32b"`).

**OpenAI gotcha:** `openai:` specs default to the **Responses API**. To use chat completions:
```python
from langchain.chat_models import init_chat_model
model = init_chat_model("openai:gpt-4.1", use_responses_api=False)
agent = create_deep_agent(model=model, ...)
```

---

## What DeepAgents does NOT provide (Quoriv must build)

- **CLI / TUI** — DeepAgents returns a `CompiledStateGraph`; we drive it with Rich + prompt_toolkit.
- **Config files** — DeepAgents takes parameters at construction time; we load them from TOML.
- **OS keychain** — we already built `quoriv.config.keychain`.
- **Tree-sitter / AST tools** — not in scope for DeepAgents; we add as plain tools.
- **Git tools** — not in scope.
- **Web search/fetch** — not in scope.
- **MCP client** — DeepAgents has no MCP integration; we connect to MCP servers and expose their tools via `tools=[]`.
- **Cost tracking** — LangSmith helps but we want a local `/cost` dashboard.
- **Trace export** — LangGraph emits events; we wire UI/log subscribers.
- **Approval prompt rendering** — `interrupt_on` pauses execution but the UI for "approve / deny / edit" is our responsibility.
- **Multi-tier permission MODES UX** — we wrap `permissions=` + `interrupt_on=` into our 4-mode model.
- **Streaming renderer** — LangGraph streams events; Rich renders them.

---

## Quoriv-specific reuse plan (replaces parts of the original plan)

### Don't build, USE
| Original plan item | DeepAgents replacement |
|---|---|
| `quoriv.tools.files` (read/write/edit/etc.) | Built-in via `FilesystemMiddleware` |
| `quoriv.tools.search.grep` | Built-in (literal substring; not regex) |
| `quoriv.tools.shell.execute` | Built-in via `LocalShellBackend` |
| `quoriv.tools.patch` | Use `edit_file` (or `multi_edit` if we add it as a custom tool) |
| `quoriv.core.runtime` (the loop) | DeepAgents' compiled graph IS the loop |
| `quoriv.core.context` (compaction) | Built-in via `SummarizationMiddleware` |
| `quoriv.memory.project` / `memory.user` | Pass paths via `memory=` |
| `quoriv.permissions.guard` / `paths` | Map to `FilesystemPermission` + path-deny rules |
| Sub-agents (researcher/debugger/etc.) | Define as `SubAgent` dicts |
| Session save/resume | LangGraph `SqliteSaver` + `thread_id` |
| Streaming events | LangGraph compiled graph's `astream_events()` |

### DO build (truly Quoriv-specific)
| Module | Purpose |
|---|---|
| `quoriv.cli` | Typer entry point + slash commands |
| `quoriv.app` | Main Rich loop driving the compiled graph |
| `quoriv.ui.*` | Streaming, diff, prompts, status, theme renderers |
| `quoriv.config.*` | Already done — TOML + keychain |
| `quoriv.models.*` | Already done — we build the `BaseChatModel` to pass to DeepAgents |
| `quoriv.permissions.modes` | Translate our 4 modes → `permissions=` + `interrupt_on=` |
| `quoriv.tools.ast_tools` | tree-sitter symbol/find_def/find_refs (plain tools) |
| `quoriv.tools.git` | git status/diff/log/commit/blame (plain tools) |
| `quoriv.tools.web` | web_search, web_fetch (plain tools) |
| `quoriv.tools.tests` | Language-aware test runner (plain tool) |
| `quoriv.plugins.mcp.*` | MCP client; connects and exposes server tools |
| `quoriv.plugins.api` | Python plugin entry-point loader |
| `quoriv.observability.cost` | Token/$ tracking via callback handlers |
| `quoriv.observability.trace` | Local JSON trace export |
| `quoriv.repo.ast` | tree-sitter parsers (powering ast_tools) |

### Stays as Quoriv design but maps to DeepAgents primitives
| Quoriv abstraction | DeepAgents primitive |
|---|---|
| `quoriv.core.agent` builder | Wraps `create_deep_agent` |
| `quoriv.core.routing` (per-task model routing) | Implement by giving each `SubAgent` its own `model=` |
| `quoriv.core.events` | Subscribe to LangGraph stream events |

---

## Common patterns / snippets

### Minimal Quoriv-style agent

```python
from deepagents import create_deep_agent, FilesystemPermission
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.sqlite import SqliteSaver

from quoriv.models import get_model
from quoriv.config import load_config

cfg = load_config()
model = get_model(cfg.model.default)

backend = LocalShellBackend(root_dir=".")

permissions = [
    FilesystemPermission(operations=["write"], paths=["/.env", "/.env.*"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/.git/**"], mode="deny"),
    FilesystemPermission(operations=["read", "write"], paths=["/.ssh/**"], mode="deny"),
]

with SqliteSaver.from_conn_string("./.quoriv/sessions.db") as saver:
    agent = create_deep_agent(
        model=model,
        backend=backend,
        permissions=permissions,
        memory=["./PROJECT.md"] if Path("./PROJECT.md").is_file() else None,
        interrupt_on={"write_file": True, "edit_file": True, "execute": True},
        checkpointer=saver,
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Read README.md and summarize."}]},
        config={"configurable": {"thread_id": "session-1"}},
    )
```

### Streaming events

```python
async for event in agent.astream_events(
    {"messages": [...]},
    config={"configurable": {"thread_id": "..."}},
    version="v2",
):
    # event["event"] is one of: "on_chat_model_start", "on_chat_model_stream",
    # "on_chat_model_end", "on_tool_start", "on_tool_end", etc.
    handle(event)
```

### Adding a custom plain tool

```python
from langchain_core.tools import tool

@tool
def find_symbol(name: str, language: str = "python") -> list[dict]:
    """Find a symbol definition across the repo using tree-sitter."""
    return ...  # quoriv.repo.symbols implementation

agent = create_deep_agent(model=..., tools=[find_symbol], ...)
```

### Defining a specialist subagent

```python
researcher: SubAgent = {
    "name": "researcher",
    "description": "Reads many files to answer questions about how the codebase works. Use for 'where is X?' or 'how does Y work?'",
    "system_prompt": "You are a thorough code researcher. Read broadly, cite specific files and line numbers.",
    "model": "openai:gpt-4o-mini",   # cheaper model for read-heavy work
    # tools and permissions inherited from main agent
}

debugger: SubAgent = {
    "name": "debugger",
    "description": "Investigates failing tests or runtime errors. Forms hypotheses, runs commands to test them.",
    "system_prompt": "You are a debugging specialist. Use the scientific method.",
    "model": "openai:gpt-4.1",
}

agent = create_deep_agent(model=..., subagents=[researcher, debugger], ...)
```

### Disabling the auto general-purpose subagent

```python
from deepagents import register_harness_profile, GeneralPurposeSubagentProfile, HarnessProfile

register_harness_profile("openai:gpt-4.1", HarnessProfile(
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
))
# Now if no subagents are passed to create_deep_agent, the `task` tool is not exposed.
```

---

## Open questions to verify before Day 5

These should be checked against the actual SDK before we commit:

1. Does `LocalShellBackend` correctly resolve relative paths to `root_dir`, or does it use process cwd?
2. How does `SummarizationMiddleware` decide token thresholds for non-Anthropic models?
3. Does the `task` tool's description get auto-populated with subagent name/description list, or do we need to format it?
4. What's the exact event schema from `astream_events(version="v2")` for Rich rendering?
5. Does `InterruptOnConfig` support arbitrary metadata for our approval UI?

Stop and read the relevant source before assuming behavior on any of these.

---

## File map (paths inside the installed package)

```
deepagents/
├── __init__.py                          # public API
├── _version.py                          # __version__ = "0.6.1"
├── graph.py                             # create_deep_agent — the entry point
├── _models.py                           # resolve_model
├── _tools.py                            # tool description override helpers
├── _excluded_middleware.py              # middleware filtering machinery
├── _messages_reducer.py                 # DeltaChannel reducer for messages
├── _subagent_transformer.py             # scope-aware subagent stream transformer
├── _api/
│   └── deprecation.py
├── backends/
│   ├── __init__.py
│   ├── protocol.py                      # BackendProtocol, SandboxBackendProtocol, ExecuteResponse, FileInfo, etc.
│   ├── state.py                         # StateBackend (default)
│   ├── filesystem.py                    # FilesystemBackend
│   ├── local_shell.py                   # LocalShellBackend (Quoriv's choice)
│   ├── store.py                         # StoreBackend
│   ├── langsmith.py                     # LangSmithSandbox
│   ├── context_hub.py                   # ContextHubBackend
│   ├── composite.py                     # CompositeBackend
│   ├── sandbox.py                       # BaseSandbox helper
│   └── utils.py                         # shared helpers
├── middleware/
│   ├── __init__.py
│   ├── filesystem.py                    # FilesystemMiddleware + FilesystemPermission
│   ├── subagents.py                     # SubAgent, CompiledSubAgent, SubAgentMiddleware
│   ├── async_subagents.py               # AsyncSubAgent, AsyncSubAgentMiddleware
│   ├── summarization.py                 # SummarizationMiddleware + create_summarization_middleware
│   ├── memory.py                        # MemoryMiddleware (AGENTS.md)
│   ├── skills.py                        # SkillsMiddleware (SKILL.md)
│   ├── permissions.py                   # legacy permission helpers
│   ├── patch_tool_calls.py              # PatchToolCallsMiddleware
│   ├── _tool_exclusion.py               # internal tool filtering
│   └── _utils.py
└── profiles/
    ├── __init__.py
    ├── _builtin_profiles.py
    ├── _keys.py
    ├── harness/
    │   ├── harness_profiles.py          # HarnessProfile, HarnessProfileConfig, GeneralPurposeSubagentProfile
    │   ├── _anthropic_sonnet_4_6.py
    │   ├── _anthropic_opus_4_7.py
    │   ├── _anthropic_haiku_4_5.py
    │   └── _openai_codex.py
    └── provider/
        ├── provider_profiles.py         # ProviderProfile, register_provider_profile
        ├── _openai.py
        └── _openrouter.py
```

When in doubt, read the source. The reference above is a working summary, not a substitute.
