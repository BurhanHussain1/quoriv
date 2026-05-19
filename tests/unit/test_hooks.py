"""Tests for ``quoriv.hooks.HookRegistry`` — Phase 3 Slice 10."""

from __future__ import annotations

from typing import Any

import pytest

from quoriv.hooks import HookRegistry


class TestRegister:
    def test_empty_registry_has_no_handlers(self) -> None:
        r = HookRegistry()
        for event in ("pre_tool", "post_tool", "on_message"):
            assert r.handlers(event) == ()  # type: ignore[arg-type]

    def test_register_adds_handler(self) -> None:
        r = HookRegistry()
        calls: list[Any] = []
        r.register("pre_tool", lambda **kw: calls.append(kw))
        assert len(r.handlers("pre_tool")) == 1

    def test_multiple_handlers_preserve_registration_order(self) -> None:
        r = HookRegistry()
        order: list[str] = []
        r.register("pre_tool", lambda **_: order.append("first"))
        r.register("pre_tool", lambda **_: order.append("second"))
        r.register("pre_tool", lambda **_: order.append("third"))
        r.fire("pre_tool")
        assert order == ["first", "second", "third"]

    def test_unknown_event_rejected(self) -> None:
        r = HookRegistry()
        with pytest.raises(ValueError, match="Unknown hook event"):
            r.register("never_heard_of_it", lambda **_: None)  # type: ignore[arg-type]


class TestFire:
    def test_fire_forwards_kwargs(self) -> None:
        r = HookRegistry()
        received: dict[str, Any] = {}
        r.register("pre_tool", lambda **kw: received.update(kw))
        r.fire("pre_tool", tool_name="execute", args={"cmd": "ls"})
        assert received == {"tool_name": "execute", "args": {"cmd": "ls"}}

    def test_fire_with_no_handlers_is_noop(self) -> None:
        # Should not raise. Many turns won't have hooks registered;
        # firing must be cheap and silent in that case.
        r = HookRegistry()
        r.fire("on_message", message="hello")

    def test_unknown_event_fire_is_silent(self) -> None:
        # Emitters know which events they fire; an unknown event
        # name in fire() is a programming error in the emitter, not
        # user input. Don't crash the turn over it.
        r = HookRegistry()
        r.fire("nope_not_real")  # type: ignore[arg-type]

    def test_callback_failure_is_logged_not_raised(self) -> None:
        r = HookRegistry()

        def boom(**_: Any) -> None:
            raise RuntimeError("simulated handler failure")

        order: list[str] = []
        r.register("post_tool", boom)
        r.register("post_tool", lambda **_: order.append("survivor"))
        # First handler raises — second still runs, no exception
        # leaks back to the caller.
        r.fire("post_tool", tool_name="x", output="y")
        assert order == ["survivor"]


class TestClear:
    def test_clear_drops_all_handlers(self) -> None:
        r = HookRegistry()
        r.register("pre_tool", lambda **_: None)
        r.register("post_tool", lambda **_: None)
        r.register("on_message", lambda **_: None)
        r.clear()
        assert r.handlers("pre_tool") == ()  # type: ignore[arg-type]
        assert r.handlers("post_tool") == ()  # type: ignore[arg-type]
        assert r.handlers("on_message") == ()  # type: ignore[arg-type]


class TestHandlersSnapshot:
    def test_returns_immutable_snapshot(self) -> None:
        r = HookRegistry()

        def cb(**_: Any) -> None:
            return None

        r.register("pre_tool", cb)
        snap = r.handlers("pre_tool")
        assert isinstance(snap, tuple)
        # Holding the snapshot doesn't mutate as more handlers register.
        r.register("pre_tool", lambda **_: None)
        assert len(snap) == 1
