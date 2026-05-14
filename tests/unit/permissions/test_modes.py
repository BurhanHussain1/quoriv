"""Tests for `quoriv.permissions.modes`."""

from __future__ import annotations

import pytest

from quoriv.permissions.modes import (
    SHELL_TOOLS,
    WRITE_TOOLS,
    interrupt_on_for_mode,
    is_read_only,
)

# ---------------------------------------------------------------------------
# Tool sets
# ---------------------------------------------------------------------------


class TestToolSets:
    def test_write_tools_includes_file_writers(self) -> None:
        assert "write_file" in WRITE_TOOLS
        assert "edit_file" in WRITE_TOOLS

    def test_shell_tools_includes_execute(self) -> None:
        assert "execute" in SHELL_TOOLS

    def test_sets_are_disjoint(self) -> None:
        assert WRITE_TOOLS.isdisjoint(SHELL_TOOLS)


# ---------------------------------------------------------------------------
# interrupt_on_for_mode
# ---------------------------------------------------------------------------


class TestInterruptOnForMode:
    def test_yolo_returns_empty_dict(self) -> None:
        assert interrupt_on_for_mode("yolo") == {}

    def test_auto_prompts_only_for_shell(self) -> None:
        result = interrupt_on_for_mode("auto")
        assert result.get("execute") is True
        assert "write_file" not in result
        assert "edit_file" not in result

    def test_ask_prompts_for_writes_and_shell(self) -> None:
        result = interrupt_on_for_mode("ask")
        assert result.get("write_file") is True
        assert result.get("edit_file") is True
        assert result.get("execute") is True

    def test_read_only_matches_ask(self) -> None:
        # Implementation detail of Phase 1 Slice 1: read-only piggybacks on
        # ask's interrupt list; the UI auto-denies writes (Slice 2). Phase 1
        # Slice 1b will add hard tool exclusion via custom middleware.
        assert interrupt_on_for_mode("read-only") == interrupt_on_for_mode("ask")

    @pytest.mark.parametrize("mode", ["yolo", "auto", "ask", "read-only"])
    def test_all_values_are_true(self, mode: str) -> None:
        result = interrupt_on_for_mode(mode)  # type: ignore[arg-type]
        assert all(v is True for v in result.values())

    def test_returns_a_fresh_dict_each_call(self) -> None:
        a = interrupt_on_for_mode("ask")
        b = interrupt_on_for_mode("ask")
        assert a == b
        assert a is not b


# ---------------------------------------------------------------------------
# is_read_only
# ---------------------------------------------------------------------------


class TestIsReadOnly:
    def test_read_only_is_true(self) -> None:
        assert is_read_only("read-only") is True

    @pytest.mark.parametrize("mode", ["ask", "auto", "yolo"])
    def test_other_modes_are_false(self, mode: str) -> None:
        assert is_read_only(mode) is False  # type: ignore[arg-type]
