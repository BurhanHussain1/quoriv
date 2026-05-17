"""Memory file resolution for ``create_deep_agent``'s ``memory=`` argument.

Quoriv passes two markdown files to DeepAgents'
:class:`MemoryMiddleware`, both optional:

    ``~/.quoriv/memory.md``   Global / per-user notes.
    ``<cwd>/PROJECT.md``      Project-specific context.

DeepAgents loads them in the order we hand them over and concatenates
them into the system prompt under ``<agent_memory>...</agent_memory>``.
We put the global file first so a project-local note can override or
refine a global one further down the prompt — same precedence rule
Quoriv's TOML loader uses (later overrides earlier).

The helpers live here (rather than inline in :mod:`quoriv.core.agent`)
so the CLI's ``/memory`` slash command and the welcome panel can show
the *same* set of files the agent actually loaded.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

QUORIV_MEMORY_FILENAME = "memory.md"
"""Name of the per-user memory file under ``~/.quoriv/``."""

PROJECT_MEMORY_FILENAME = "PROJECT.md"
"""Name of the per-project memory file at the repo root."""


PROJECT_MEMORY_TEMPLATE = """\
# Project memory

Quoriv reads this file at session start and injects it into the
agent's system prompt under ``<agent_memory>``. Keep it short and
high-signal — every token here costs context.

## Project overview

One paragraph: what this repo is, who it's for, what problem it
solves. Link to a README or design doc for the full story.

## Architecture (one screen max)

- Top-level layout: …
- Key entry points: …
- Important invariants: …

## Conventions

- Code style / naming patterns the agent should follow.
- Test conventions (framework, where tests live, how to run a subset).
- Anything non-obvious about the build or release flow.

## Useful commands

```
# Run all tests
…

# Lint
…

# Local dev
…
```

## Things to avoid

- Files / directories the agent must not edit (most are already
  covered by Quoriv's built-in PATH_PROTECTION — list anything
  extra here).
- Common dead-ends or wrong-but-tempting refactors.
"""
"""Default content for a freshly-scaffolded ``PROJECT.md``.

Designed to fit on one screen so a user reading ``quoriv init``'s
output can scan the structure without scrolling. Each section is
short, scannable, and points the user at the kind of content that
actually helps an LLM rather than at boilerplate.
"""


class MemoryCandidate(NamedTuple):
    """One memory file Quoriv would hand to DeepAgents if present.

    ``label`` is the user-facing tag (``"global"`` / ``"project"``)
    used by the CLI's ``/memory`` listing.
    """

    label: str
    path: Path


def memory_candidates(cwd: Path) -> list[MemoryCandidate]:
    """Return the ordered list of memory paths Quoriv considers.

    The list is always two entries — global first, then project — so
    callers that want to render both present and missing files can
    iterate it directly. Use :func:`resolve_memory_files` when you
    only want files that actually exist.
    """
    return [
        MemoryCandidate("global", Path.home() / ".quoriv" / QUORIV_MEMORY_FILENAME),
        MemoryCandidate("project", cwd / PROJECT_MEMORY_FILENAME),
    ]


def resolve_memory_files(cwd: Path) -> list[Path]:
    """Return memory file paths that actually exist, in load order.

    The returned list is what gets handed to
    ``create_deep_agent(memory=...)``. An empty list means no memory
    files are present — callers should typically pass ``None`` to
    DeepAgents in that case so the middleware isn't added.
    """
    return [candidate.path for candidate in memory_candidates(cwd) if candidate.path.is_file()]
