"""Slash-command autocomplete — Phase 5 Slices 1 and 3.

A :class:`prompt_toolkit.completion.Completer` that fires whenever the
buffer contains a leading ``/`` and surfaces:

* **Command-name completions** — when the user is still typing the
  command itself (``/mo`` → ``/mode``, ``/me`` → ``/memory``). The
  popup includes the canonical name and the description in the meta
  column. Non-slash input gets zero completions, so a chat message
  containing ``/tmp/foo`` doesn't trigger a popup.

* **Argument completions** — when the user has typed a known command
  followed by a space, the completer looks up the registered
  ``argument_providers`` mapping and yields the dynamic argument
  values. The popup looks identical to the command popup so the user
  experience is Claude-Code-style inline typeahead:
  ``/mode <Down-arrow><Enter>`` cycles to ``/mode auto`` in the
  buffer with no separate modal step.

The argument providers are zero-arg callables so dynamic values (e.g.
the live list of saved sessions for ``/load``) stay in sync without
the completer needing to mutate state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document


ArgumentProvider = "Callable[[], list[tuple[str, str]]]"
"""Type alias documenting the shape of an argument provider.

A provider returns a list of ``(value, description)`` pairs. ``value``
is what gets inserted into the buffer; ``description`` shows in the
completion popup's meta column.
"""


class SlashCommandCompleter(Completer):
    """Suggest slash commands and their arguments as the user types.

    Args:
        commands: ``{name: description}`` map. ``name`` must include
            the leading ``/``. Lookup is case-insensitive against the
            user-typed prefix; the canonical casing from this dict is
            what gets inserted on completion. The command insertion
            ends with a trailing space so the user can flow straight
            into argument completion.
        argument_providers: Optional ``{name: callable}`` map. When
            the user has typed ``<name> `` (command + space) the
            callable is invoked and its returned ``(value, meta)``
            pairs are surfaced as inline completions. Missing entries
            (commands with no argument completions) simply yield no
            argument-phase suggestions — the user can still type
            free-form arguments.
    """

    def __init__(
        self,
        commands: dict[str, str],
        *,
        argument_providers: dict[str, Callable[[], list[tuple[str, str]]]] | None = None,
    ) -> None:
        self._commands = commands
        self._argument_providers = argument_providers or {}

    def get_completions(
        self,
        document: Document,
        _complete_event: CompleteEvent,
    ) -> Iterator[Completion]:
        """Yield completions for the current ``Document``.

        Two phases:

        1. **Command phase** — buffer starts with ``/`` and contains
           no whitespace yet. Suggest matching command names.
        2. **Argument phase** — buffer starts with a known command
           followed by a single space. Suggest values from the
           registered provider, filtered by the partial argument
           text the user has typed.

        Anything else (no leading ``/``, mid-prompt slash, unknown
        command with whitespace) yields nothing — the user sees no
        popup.
        """
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        if " " not in text:
            # Command-name phase. Append a trailing space only for
            # commands that have an argument provider — that way
            # Enter on ``/mode`` reopens the menu for the mode list
            # but Enter on ``/help`` (no args) submits immediately
            # rather than leaving a stray space the user has to
            # delete.
            prefix = text.lower()
            for name, desc in self._commands.items():
                if name.lower().startswith(prefix):
                    insert = name + " " if name.lower() in self._argument_providers else name
                    yield Completion(
                        insert,
                        start_position=-len(text),
                        display=name,
                        display_meta=desc,
                    )
            return

        # Argument phase — the command is everything before the first
        # space; the cursor is somewhere in the argument tail.
        cmd, _, arg_text = text.partition(" ")
        cmd_lower = cmd.lower()
        provider = self._argument_providers.get(cmd_lower)
        if provider is None:
            return

        # ``arg_text`` is everything after the first space, including
        # any further spaces. For now we only complete the *first*
        # argument token — subsequent tokens are free-form. Strip the
        # leading whitespace the partition left behind.
        arg_prefix = arg_text.lstrip()
        # ``start_position`` is negative: number of chars from the
        # cursor back to where the inserted text should overwrite. We
        # want to replace from the start of the current argument
        # token, so it's -(len of the prefix typed so far).
        start_pos = -len(arg_prefix)

        prefix_lower = arg_prefix.lower()
        try:
            options = provider()
        except Exception:  # pragma: no cover — defensive against broken providers
            return
        for value, meta in options:
            if not isinstance(value, str):
                continue
            if value.lower().startswith(prefix_lower):
                yield Completion(
                    value,
                    start_position=start_pos,
                    display=value,
                    display_meta=meta,
                )
