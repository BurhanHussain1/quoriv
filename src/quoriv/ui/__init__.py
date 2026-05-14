"""Terminal UI rendering.

All Rich + prompt_toolkit code lives here. The agent core is unaware of
this package; ``quoriv.app`` is the consumer that wires UI helpers to
events emitted by the compiled DeepAgent.

Modules:
    prompts     Approval prompts for HITL-gated tool calls
                (``prompt_approval``, ``ApprovalDecision``).
    chat        (later) The main scroll-based chat view.
    stream      (later) Token-streaming renderer with markdown polish.
    diff        (later) Diff display for proposed file edits.
    slash       (later) Slash command parsing and dispatch helpers.
    status      (later) Persistent status line (model, tokens, cost, branch).
    theme       (later) Color theme registry.
"""

from __future__ import annotations

from quoriv.ui.prompts import (
    READ_ONLY_DENIAL_MESSAGE,
    ApprovalDecision,
    DecisionType,
    parse_choice,
    prompt_approval,
)

__all__ = [
    "READ_ONLY_DENIAL_MESSAGE",
    "ApprovalDecision",
    "DecisionType",
    "parse_choice",
    "prompt_approval",
]
