"""Tests for `quoriv.ui.prompts`.

The interactive ``prompt_approval`` path that reads from stdin is
exercised by integration tests in a later slice — unit-testing it
requires stubbing ``prompt_toolkit``, which adds little value. We test
the ``auto_deny`` path (no input needed) and the pure-function pieces.
"""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from quoriv.ui.prompts import (
    READ_ONLY_DENIAL_MESSAGE,
    ApprovalDecision,
    _format_args,
    _render_approval_panel,
    parse_choice,
    prompt_approval,
)


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False, no_color=True)
    return console, buf


# ---------------------------------------------------------------------------
# parse_choice
# ---------------------------------------------------------------------------


class TestParseChoice:
    @pytest.mark.parametrize("raw", ["a", "approve", "y", "yes", "A", " yes  ", "Approve"])
    def test_approve_aliases(self, raw: str) -> None:
        assert parse_choice(raw) == "approve"

    @pytest.mark.parametrize("raw", ["r", "reject", "n", "no", "deny", "R", " no "])
    def test_reject_aliases(self, raw: str) -> None:
        assert parse_choice(raw) == "reject"

    @pytest.mark.parametrize("raw", ["", " ", "maybe", "skip", "ok", "approveplease"])
    def test_invalid_returns_none(self, raw: str) -> None:
        assert parse_choice(raw) is None


# ---------------------------------------------------------------------------
# ApprovalDecision
# ---------------------------------------------------------------------------


class TestApprovalDecision:
    def test_default_message_is_none(self) -> None:
        d = ApprovalDecision(type="approve")
        assert d.message is None

    def test_with_message(self) -> None:
        d = ApprovalDecision(type="reject", message="nope")
        assert d.type == "reject"
        assert d.message == "nope"

    def test_is_frozen(self) -> None:
        d = ApprovalDecision(type="approve")
        with pytest.raises(Exception):  # noqa: B017 — FrozenInstanceError or AttributeError
            d.type = "reject"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# auto_deny path of prompt_approval
# ---------------------------------------------------------------------------


class TestPromptApprovalAutoDeny:
    async def test_returns_reject_with_read_only_message(self) -> None:
        console, buf = _make_console()
        result = await prompt_approval(
            console,
            tool_name="edit_file",
            tool_args={"file_path": "/foo.py", "old_string": "x", "new_string": "y"},
            auto_deny=True,
        )
        assert result.type == "reject"
        assert result.message == READ_ONLY_DENIAL_MESSAGE
        # The panel renders the tool name even in auto-deny mode so the user
        # sees what was blocked.
        out = buf.getvalue()
        assert "edit_file" in out
        assert "Auto-denied" in out


# ---------------------------------------------------------------------------
# Internal renderers
# ---------------------------------------------------------------------------


class TestRenderApprovalPanel:
    def test_includes_tool_name_and_args(self) -> None:
        console, buf = _make_console()
        _render_approval_panel(console, "write_file", {"file_path": "/x"}, None)
        out = buf.getvalue()
        assert "write_file" in out
        assert "/x" in out

    def test_includes_description_when_provided(self) -> None:
        console, buf = _make_console()
        _render_approval_panel(console, "execute", {"cmd": "ls"}, "Run shell command")
        out = buf.getvalue()
        assert "Run shell command" in out


class TestFormatArgs:
    def test_serializable_args(self) -> None:
        out = _format_args({"a": 1, "b": "x"})
        assert '"a": 1' in out
        assert '"b": "x"' in out

    def test_unserializable_falls_back_to_repr(self) -> None:
        # default=str handles most non-JSON values; ensure no crash.
        out = _format_args({"path": object()})
        assert isinstance(out, str)
        assert len(out) > 0
