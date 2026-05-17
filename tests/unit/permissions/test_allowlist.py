"""Tests for ``quoriv.permissions.allowlist`` — Phase 2 Slice 3."""

from __future__ import annotations

from quoriv.permissions import SessionAllowlist


class TestSessionAllowlist:
    def test_empty_by_default(self) -> None:
        allowlist = SessionAllowlist()
        assert len(allowlist) == 0
        assert "execute" not in allowlist

    def test_allow_adds_tool(self) -> None:
        allowlist = SessionAllowlist()
        allowlist.allow("execute")
        assert "execute" in allowlist
        assert len(allowlist) == 1

    def test_allow_is_idempotent(self) -> None:
        # Adding the same tool twice is a no-op rather than an error —
        # the chat loop may unconditionally re-promote a tool every
        # time the user picks ``approve_always``.
        allowlist = SessionAllowlist()
        allowlist.allow("write_file")
        allowlist.allow("write_file")
        assert len(allowlist) == 1

    def test_contains_returns_false_for_non_string(self) -> None:
        # The ``in`` check must tolerate any object — Python's
        # ``in`` protocol invokes ``__contains__`` with whatever the
        # left operand is.
        allowlist = SessionAllowlist()
        allowlist.allow("execute")
        assert 42 not in allowlist  # type: ignore[operator]
        assert None not in allowlist  # type: ignore[operator]

    def test_tools_returns_frozenset_snapshot(self) -> None:
        # Snapshot returned to callers should be immutable so they
        # can't accidentally mutate the live allowlist by holding the
        # reference around.
        allowlist = SessionAllowlist()
        allowlist.allow("a")
        allowlist.allow("b")
        snapshot = allowlist.tools()
        assert isinstance(snapshot, frozenset)
        assert snapshot == frozenset({"a", "b"})
        # Mutating the live allowlist must not retroactively change
        # the snapshot.
        allowlist.allow("c")
        assert "c" not in snapshot

    def test_clear_drops_all_entries(self) -> None:
        allowlist = SessionAllowlist()
        allowlist.allow("execute")
        allowlist.allow("write_file")
        allowlist.clear()
        assert len(allowlist) == 0
        assert "execute" not in allowlist

    def test_multiple_tools_tracked_independently(self) -> None:
        allowlist = SessionAllowlist()
        allowlist.allow("execute")
        assert "execute" in allowlist
        assert "write_file" not in allowlist
        allowlist.allow("write_file")
        assert "execute" in allowlist
        assert "write_file" in allowlist
