"""Slash-command autocomplete — Phase 5 Slice 1 (UI polish).

A :class:`prompt_toolkit.completion.Completer` that fires whenever the
buffer contains a leading ``/`` followed by a partial command. The
completer surfaces matching commands from the supplied
``slash_commands`` mapping, with the description shown in the popup
metadata column. Non-slash input passes through with zero
completions — the user sees no popup mid-prompt.

Pure data: the completer receives the command dict directly so the
list stays in sync with whatever the chat loop exposes via
:func:`quoriv.app._handle_slash`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion

if TYPE_CHECKING:
    from collections.abc import Iterator

    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document


class SlashCommandCompleter(Completer):
    """Suggest slash commands as the user types ``/`` then a prefix.

    Args:
        commands: ``{name: description}`` map. ``name`` must include
            the leading ``/``. Lookup is case-insensitive against the
            user-typed prefix; the canonical casing from this dict is
            what gets inserted on completion.
    """

    def __init__(self, commands: dict[str, str]) -> None:
        self._commands = commands

    def get_completions(
        self,
        document: Document,
        _complete_event: CompleteEvent,
    ) -> Iterator[Completion]:
        """Yield completions for the current ``Document``.

        The popup fires only when:
        - the buffer starts with ``/``, and
        - the user is still typing the command token (no whitespace yet)
        so a request mid-prompt (``Tell me about /tmp``) doesn't get a
        slash popup.
        """
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        # Bail once the user has moved past the command word — args
        # belong to the command, not the completer.
        if " " in text:
            return

        prefix = text.lower()
        for name, desc in self._commands.items():
            if name.lower().startswith(prefix):
                yield Completion(
                    name,
                    start_position=-len(text),
                    display=name,
                    display_meta=desc,
                )
