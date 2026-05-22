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


# ---------------------------------------------------------------------------
# Slice 3: inline argument completions
# ---------------------------------------------------------------------------


_ARG_COMMANDS = {
    "/mode": "Switch permission mode",
    "/load": "Load a saved session",
    "/help": "Show help",
}


def _arg_completions(buffer_text: str) -> list[tuple[str, str]]:
    """Run the arg-aware completer and return (text, meta) pairs."""
    doc = Document(text=buffer_text, cursor_position=len(buffer_text))
    completer = SlashCommandCompleter(
        _ARG_COMMANDS,
        argument_providers={
            "/mode": lambda: [
                ("read-only", "investigation only"),
                ("ask", "prompt before writes"),
                ("auto", "auto-approve writes"),
                ("yolo", "no prompts"),
            ],
            "/load": lambda: [
                ("session-one", "2026-05-01"),
                ("session-two", "2026-05-23"),
            ],
        },
    )
    return [(c.text, c.display_meta_text) for c in completer.get_completions(doc, CompleteEvent())]


class TestSlashCompleterArguments:
    def test_command_with_arg_provider_gets_trailing_space(self) -> None:
        # ``/mode`` has an arg provider — completion should insert
        # ``/mode `` (with trailing space) so the menu re-opens for
        # the argument list once the user accepts.
        texts = {text for text, _ in _arg_completions("/mod")}
        assert "/mode " in texts

    def test_command_without_arg_provider_has_no_trailing_space(self) -> None:
        # ``/help`` has no arg provider — no trailing space, so the
        # user can hit Enter and submit immediately.
        texts = {text for text, _ in _arg_completions("/help")}
        assert "/help" in texts
        assert "/help " not in texts

    def test_argument_phase_yields_provider_values(self) -> None:
        # After ``/mode `` (with trailing space) the completer
        # switches to argument phase and surfaces every value from
        # the provider.
        values = [text for text, _ in _arg_completions("/mode ")]
        assert set(values) == {"read-only", "ask", "auto", "yolo"}

    def test_argument_prefix_filters_provider_values(self) -> None:
        # Partial argument text narrows the completion set.
        values = [text for text, _ in _arg_completions("/mode a")]
        assert set(values) == {"ask", "auto"}

    def test_argument_phase_meta_comes_from_provider(self) -> None:
        # The second element of each ``(value, meta)`` pair from the
        # provider lands in the popup's meta column.
        pairs = _arg_completions("/mode auto")
        assert pairs == [("auto", "auto-approve writes")]

    def test_argument_phase_case_insensitive(self) -> None:
        values = {text for text, _ in _arg_completions("/mode A")}
        assert "auto" in values
        assert "ask" in values

    def test_unknown_command_argument_phase_yields_nothing(self) -> None:
        # No arg provider registered for ``/quit`` → no argument-
        # phase completions. The user can still type free-form.
        assert _arg_completions("/quit foo") == []

    def test_load_provider_is_called_per_completion_request(self) -> None:
        # The provider closure resolves a list at call time so dynamic
        # data (e.g. saved sessions appearing during the chat) shows
        # up without rebuilding the completer.
        calls: list[int] = []

        def provider() -> list[tuple[str, str]]:
            calls.append(1)
            return [("alpha", "first"), ("beta", "second")]

        completer = SlashCommandCompleter(
            {"/load": "load"},
            argument_providers={"/load": provider},
        )
        doc = Document(text="/load ", cursor_position=6)
        list(completer.get_completions(doc, CompleteEvent()))
        list(completer.get_completions(doc, CompleteEvent()))
        assert len(calls) == 2  # called once per completion request
