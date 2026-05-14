"""Terminal UI rendering.

All Rich + prompt_toolkit code lives here. The agent core is unaware of
this package; ``quoriv.app`` is the consumer that wires UI helpers to
events emitted by the compiled DeepAgent.

Modules:
    prompts     Approval prompts for HITL-gated tool calls
                (``prompt_approval``, ``ApprovalDecision``).
    stream      Streaming markdown renderer (``StreamRenderer``).
    diff        Unified-diff rendering for proposed file edits
                (``render_edit_diff``, ``compute_diff``).
    chat        (later) The main scroll-based chat view.
    slash       (later) Slash command parsing and dispatch helpers.
    status      (later) Persistent status line (model, tokens, cost, branch).
    theme       (later) Color theme registry.
"""

from __future__ import annotations

from quoriv.ui.diff import compute_diff, render_edit_diff
from quoriv.ui.prompts import (
    READ_ONLY_DENIAL_MESSAGE,
    ApprovalDecision,
    DecisionType,
    parse_choice,
    prompt_approval,
)
from quoriv.ui.stream import StreamRenderer

__all__ = [
    "READ_ONLY_DENIAL_MESSAGE",
    "ApprovalDecision",
    "DecisionType",
    "StreamRenderer",
    "compute_diff",
    "parse_choice",
    "prompt_approval",
    "render_edit_diff",
]
