"""Tests for ``quoriv.ui.slash_completer`` — Phase 5 Slice 1."""

from __future__ import annotations

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from quoriv.ui.slash_completer import SlashCommandCompleter

_COMMANDS = {
    "/help": "List slash commands",
    "/exit": "Leave the session",
    "/quit": "Leave the session (alias)",
    "/clear": "Start a fresh thread",
    "/cost": "Show approximate session cost",
}


def _completions(buffer_text: str) -> list[tuple[str, str]]:
    """Run the completer against ``buffer_text`` and return (text, meta)."""
    doc = Document(text=buffer_text, cursor_position=len(buffer_text))
    completer = SlashCommandCompleter(_COMMANDS)
    return [(c.text, c.display_meta_text) for c in completer.get_completions(doc, CompleteEvent())]


class TestSlashCompleter:
    def test_empty_buffer_yields_nothing(self) -> None:
        # No slash → no popup. Critical: completer must stay silent on
        # regular freeform prompts.
        assert _completions("") == []

    def test_non_slash_buffer_yields_nothing(self) -> None:
        assert _completions("fix the bug") == []

    def test_bare_slash_matches_every_command(self) -> None:
        names = {text for text, _ in _completions("/")}
        assert names == set(_COMMANDS.keys())

    def test_prefix_filters_commands(self) -> None:
        names = [text for text, _ in _completions("/c")]
        # Both /clear and /cost start with `/c`.
        assert set(names) == {"/clear", "/cost"}

    def test_exact_command_still_completes_itself(self) -> None:
        # Power user types the full command then waits — popup should
        # still show that single match so the description is visible.
        names = [text for text, _ in _completions("/help")]
        assert names == ["/help"]

    def test_case_insensitive_match(self) -> None:
        # User typing /CL should still find /clear — typing case is
        # an annoyance, not a filter.
        names = [text for text, _ in _completions("/CL")]
        assert "/clear" in names

    def test_description_shown_as_meta(self) -> None:
        completions = _completions("/help")
        assert completions == [("/help", "List slash commands")]

    def test_no_match_yields_empty(self) -> None:
        # `/zzz` matches nothing — popup must collapse, not surface
        # everything as a fallback.
        assert _completions("/zzz") == []

    def test_post_arg_text_does_not_re_trigger(self) -> None:
        # Once the user has moved past the command word into args
        # (`/load my-session`), the completer should bail — args
        # belong to the command, not the completer.
        assert _completions("/load my") == []

    def test_freeform_with_slash_path_does_not_trigger(self) -> None:
        # `Tell me about /tmp/foo` starts with a non-slash character
        # so the early-return guards the popup cleanly.
        assert _completions("Tell me about /tmp/foo") == []
