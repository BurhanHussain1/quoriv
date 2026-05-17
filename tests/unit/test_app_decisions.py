"""Tests for HITL decision plumbing in ``quoriv.app``.

Phase 2 Slice 3 introduces the session allowlist and the
``approve_always`` decision kind. These tests focus on the two
helpers that bridge ``prompt_approval`` and DeepAgents' HITL resume
schema: ``_collect_decisions`` (the allowlist short-circuit + the
``approve_always`` → allowlist promotion) and ``_decision_payload``
(the wire-format conversion).
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from rich.console import Console

from quoriv.app import _collect_decisions, _decision_payload
from quoriv.permissions import SessionAllowlist
from quoriv.ui.prompts import ApprovalDecision


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(file=buf, width=10_000, force_terminal=False, no_color=True), buf


def _hitl_request(*tool_names: str) -> dict[str, Any]:
    """Build a minimal HITL request with ``action_requests`` for each tool."""
    return {
        "action_requests": [{"name": name, "args": {}} for name in tool_names],
    }


def _patch_prompt(
    monkeypatch: pytest.MonkeyPatch,
    *,
    decision_factory: Any,
) -> list[str]:
    """Replace ``prompt_approval`` with a stub that records each call.

    Returns a list that will be populated with the tool names the stub
    was asked about — so a test can assert "was/wasn't prompted for X".
    """
    seen: list[str] = []

    async def fake_prompt(
        console: Console,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        description: str | None = None,
        auto_deny: bool = False,
    ) -> ApprovalDecision:
        seen.append(tool_name)
        return decision_factory(tool_name)

    monkeypatch.setattr("quoriv.app.prompt_approval", fake_prompt)
    return seen


# ---------------------------------------------------------------------------
# _decision_payload — wire-format conversion
# ---------------------------------------------------------------------------


class TestDecisionPayload:
    def test_approve_passthrough(self) -> None:
        assert _decision_payload(ApprovalDecision(type="approve")) == {"type": "approve"}

    def test_reject_includes_message(self) -> None:
        assert _decision_payload(ApprovalDecision(type="reject", message="nope")) == {
            "type": "reject",
            "message": "nope",
        }

    def test_approve_always_maps_to_approve(self) -> None:
        # DeepAgents only knows approve/reject/edit/respond. The
        # ``approve_always`` signal must be reduced to plain ``approve``
        # on the wire — the allowlist promotion happens elsewhere.
        assert _decision_payload(ApprovalDecision(type="approve_always")) == {"type": "approve"}


# ---------------------------------------------------------------------------
# _collect_decisions — allowlist short-circuit and promotion
# ---------------------------------------------------------------------------


class TestCollectDecisionsAllowlist:
    async def test_allowlisted_tool_skips_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # When a tool is already on the allowlist, no prompt should
        # be rendered — the decision auto-resolves to approve.
        seen = _patch_prompt(monkeypatch, decision_factory=lambda _t: ApprovalDecision("approve"))
        allowlist = SessionAllowlist()
        allowlist.allow("execute")
        console, buf = _make_console()
        decisions = await _collect_decisions(
            console,
            _hitl_request("execute"),
            auto_deny=False,
            allowlist=allowlist,
        )
        assert decisions == [{"type": "approve"}]
        assert seen == []  # prompt never called
        assert "auto-approved" in buf.getvalue()

    async def test_non_allowlisted_tool_still_prompts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _patch_prompt(monkeypatch, decision_factory=lambda _t: ApprovalDecision("approve"))
        allowlist = SessionAllowlist()
        allowlist.allow("execute")
        console, _buf = _make_console()
        decisions = await _collect_decisions(
            console,
            _hitl_request("write_file"),
            auto_deny=False,
            allowlist=allowlist,
        )
        assert decisions == [{"type": "approve"}]
        assert seen == ["write_file"]

    async def test_approve_always_promotes_tool_to_allowlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # First call: user picks approve_always. The tool should land
        # on the allowlist so the *next* prompt for the same tool is
        # skipped.
        _patch_prompt(
            monkeypatch,
            decision_factory=lambda _t: ApprovalDecision("approve_always"),
        )
        allowlist = SessionAllowlist()
        console, buf = _make_console()
        decisions = await _collect_decisions(
            console,
            _hitl_request("execute"),
            auto_deny=False,
            allowlist=allowlist,
        )
        # Wire payload is plain approve (DeepAgents doesn't speak
        # approve_always); the allowlist captures the persistence.
        assert decisions == [{"type": "approve"}]
        assert "execute" in allowlist
        assert "Will auto-approve" in buf.getvalue()

    async def test_subsequent_call_uses_promoted_allowlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Same flow as above, then a second call exercises the
        # short-circuit. Prompts should be invoked only once.
        calls: list[str] = []

        async def fake_prompt(
            console: Console,
            *,
            tool_name: str,
            tool_args: dict[str, Any],
            description: str | None = None,
            auto_deny: bool = False,
        ) -> ApprovalDecision:
            calls.append(tool_name)
            return ApprovalDecision(type="approve_always")

        monkeypatch.setattr("quoriv.app.prompt_approval", fake_prompt)
        allowlist = SessionAllowlist()
        console, _buf = _make_console()
        await _collect_decisions(
            console,
            _hitl_request("execute"),
            auto_deny=False,
            allowlist=allowlist,
        )
        await _collect_decisions(
            console,
            _hitl_request("execute"),
            auto_deny=False,
            allowlist=allowlist,
        )
        assert calls == ["execute"]  # prompted only the first time

    async def test_auto_deny_overrides_allowlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Read-only mode (``auto_deny=True``) must trump the allowlist.
        # A previously remembered approval doesn't unlock read-only.
        seen = _patch_prompt(
            monkeypatch,
            decision_factory=lambda _t: ApprovalDecision("reject", message="auto-denied"),
        )
        allowlist = SessionAllowlist()
        allowlist.allow("write_file")
        console, _buf = _make_console()
        decisions = await _collect_decisions(
            console,
            _hitl_request("write_file"),
            auto_deny=True,
            allowlist=allowlist,
        )
        assert decisions == [{"type": "reject", "message": "auto-denied"}]
        # Prompt was *still* invoked (it renders the panel in auto_deny
        # mode then short-circuits internally), but the allowlist did
        # not skip it.
        assert seen == ["write_file"]

    async def test_none_allowlist_behaves_like_legacy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Older callers (and the existing E2E test) pass no allowlist.
        # Every action must still be prompted.
        seen = _patch_prompt(
            monkeypatch,
            decision_factory=lambda _t: ApprovalDecision("approve"),
        )
        console, _buf = _make_console()
        decisions = await _collect_decisions(
            console,
            _hitl_request("execute"),
            auto_deny=False,
            allowlist=None,
        )
        assert decisions == [{"type": "approve"}]
        assert seen == ["execute"]
