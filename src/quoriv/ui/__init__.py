"""Terminal UI rendering.

All Rich + prompt_toolkit code lives here. The agent core is unaware of
this package; the UI subscribes to events emitted by core.events.

Modules:
    chat        The main scroll-based chat view.
    stream      Token-streaming renderer for model output.
    diff        Diff display for proposed file edits.
    prompts     Approval prompts for permission-gated tools.
    slash       Slash command parsing and dispatch.
    status      Persistent status line (model, tokens, cost, branch).
    theme       Color theme registry.
"""
