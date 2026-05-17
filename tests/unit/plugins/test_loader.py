"""Tests for ``quoriv.plugins.loader`` — Phase 2 Slice 5.

The loader walks ``importlib.metadata.entry_points`` for the
``quoriv.plugins`` group. We monkeypatch that helper to inject fake
entry points so tests don't depend on actually-installed packages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from langchain_core.tools import tool

from quoriv.plugins.loader import (
    PluginRecord,
    discover_plugin_tools,
    list_plugins,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# Test infrastructure — fake entry points
# ---------------------------------------------------------------------------


class _FakeEntryPoint:
    """Minimal stand-in for ``importlib.metadata.EntryPoint``.

    The loader only touches ``name``, ``value``, and ``load`` — so a
    light-weight stub is enough to exercise the real loader code path
    without installing test packages.
    """

    def __init__(self, name: str, value: str, factory: Callable[[], Any]) -> None:
        self.name = name
        self.value = value
        self._factory = factory

    def load(self) -> Callable[[], Any]:
        return self._factory


@tool
def _echo(text: str) -> str:
    """Tiny @tool used as a stand-in for a plugin-provided tool."""
    return text


@tool
def _greet(name: str) -> str:
    """Another stand-in tool — distinguishes which plugin contributed it."""
    return f"hello {name}"


def _stub_entry_points(monkeypatch: pytest.MonkeyPatch, eps: list[_FakeEntryPoint]) -> None:
    monkeypatch.setattr(
        "quoriv.plugins.loader._list_entry_points",
        lambda: list(eps),
    )


# ---------------------------------------------------------------------------
# discover_plugin_tools — happy paths
# ---------------------------------------------------------------------------


class TestDiscoverPluginTools:
    def test_empty_when_no_entry_points(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_entry_points(monkeypatch, [])
        assert discover_plugin_tools() == []

    def test_loads_one_plugin_with_one_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_entry_points(
            monkeypatch,
            [_FakeEntryPoint("echo_plugin", "fake_pkg:factory", lambda: [_echo])],
        )
        tools = discover_plugin_tools()
        assert [t.name for t in tools] == ["_echo"]

    def test_merges_tools_from_multiple_plugins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_entry_points(
            monkeypatch,
            [
                _FakeEntryPoint("p1", "pkg1:factory", lambda: [_echo]),
                _FakeEntryPoint("p2", "pkg2:factory", lambda: [_greet]),
            ],
        )
        tools = discover_plugin_tools()
        names = {t.name for t in tools}
        assert names == {"_echo", "_greet"}

    def test_accepts_generator_returns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Plugins can return an iterator/generator, not just a list.
        # The loader normalises to a list internally.
        def factory() -> Any:
            yield _echo
            yield _greet

        _stub_entry_points(monkeypatch, [_FakeEntryPoint("gen", "pkg:gen", factory)])
        tools = discover_plugin_tools()
        assert {t.name for t in tools} == {"_echo", "_greet"}


# ---------------------------------------------------------------------------
# discover_plugin_tools — disabled list
# ---------------------------------------------------------------------------


class TestDisabledFiltering:
    def test_disabled_plugin_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_entry_points(
            monkeypatch,
            [
                _FakeEntryPoint("noisy", "pkg:bad", lambda: [_echo]),
                _FakeEntryPoint("keep", "pkg:ok", lambda: [_greet]),
            ],
        )
        tools = discover_plugin_tools(disabled=["noisy"])
        assert [t.name for t in tools] == ["_greet"]

    def test_disabled_can_be_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The disabled arg accepts any iterable, not only list.
        _stub_entry_points(
            monkeypatch,
            [_FakeEntryPoint("noisy", "pkg:bad", lambda: [_echo])],
        )
        assert discover_plugin_tools(disabled={"noisy"}) == []

    def test_empty_disabled_loads_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_entry_points(
            monkeypatch,
            [_FakeEntryPoint("keep", "pkg:ok", lambda: [_echo])],
        )
        assert len(discover_plugin_tools(disabled=[])) == 1


# ---------------------------------------------------------------------------
# discover_plugin_tools — defensive paths
# ---------------------------------------------------------------------------


class TestDefensiveLoading:
    def test_import_error_logs_and_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A plugin whose entry point fails to import must not break
        # the rest of the session — log and continue.
        def boom() -> Any:
            raise ImportError("simulated import failure")

        class _BrokenEntryPoint(_FakeEntryPoint):
            def load(self) -> Callable[[], Any]:
                raise ImportError("simulated import failure")

        _stub_entry_points(
            monkeypatch,
            [
                _BrokenEntryPoint("broken", "pkg:nope", boom),
                _FakeEntryPoint("ok", "pkg:ok", lambda: [_echo]),
            ],
        )
        tools = discover_plugin_tools()
        # The working plugin still loads.
        assert [t.name for t in tools] == ["_echo"]

    def test_factory_raising_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def explodes() -> Any:
            raise RuntimeError("factory exploded")

        _stub_entry_points(
            monkeypatch,
            [
                _FakeEntryPoint("bad", "pkg:bad", explodes),
                _FakeEntryPoint("ok", "pkg:ok", lambda: [_echo]),
            ],
        )
        tools = discover_plugin_tools()
        assert [t.name for t in tools] == ["_echo"]

    def test_non_iterable_return_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_entry_points(
            monkeypatch,
            [_FakeEntryPoint("scalar", "pkg:scalar", lambda: 42)],
        )
        assert discover_plugin_tools() == []

    def test_non_tool_items_are_filtered_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A plugin that mixes valid tools with garbage should still
        # contribute the valid ones.
        _stub_entry_points(
            monkeypatch,
            [_FakeEntryPoint("mixed", "pkg:mixed", lambda: [_echo, "not a tool", 42])],
        )
        tools = discover_plugin_tools()
        assert [t.name for t in tools] == ["_echo"]


# ---------------------------------------------------------------------------
# list_plugins — introspection view
# ---------------------------------------------------------------------------


class TestListPlugins:
    def test_records_for_each_entry_point(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_entry_points(
            monkeypatch,
            [
                _FakeEntryPoint("a", "pkg_a:factory", lambda: [_echo]),
                _FakeEntryPoint("b", "pkg_b:factory", lambda: [_greet]),
            ],
        )
        records = list_plugins()
        assert [r.name for r in records] == ["a", "b"]
        assert all(isinstance(r, PluginRecord) for r in records)
        # Tool names captured for each.
        names_by_plugin = {r.name: r.tool_names for r in records}
        assert names_by_plugin["a"] == ("_echo",)
        assert names_by_plugin["b"] == ("_greet",)

    def test_captures_load_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BrokenEntryPoint(_FakeEntryPoint):
            def load(self) -> Callable[[], Any]:
                raise ImportError("nope")

        _stub_entry_points(monkeypatch, [_BrokenEntryPoint("broken", "pkg:broken", lambda: [])])
        record = list_plugins()[0]
        assert record.name == "broken"
        assert record.error is not None
        assert "nope" in record.error
        assert record.tool_names == ()

    def test_captures_factory_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def explodes() -> Any:
            raise RuntimeError("boom")

        _stub_entry_points(monkeypatch, [_FakeEntryPoint("bad", "pkg:bad", explodes)])
        record = list_plugins()[0]
        assert record.error is not None
        assert "boom" in record.error
