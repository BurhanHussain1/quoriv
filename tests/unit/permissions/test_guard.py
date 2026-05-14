"""Tests for `quoriv.permissions.guard`.

We don't spin up a real DeepAgent here — that's integration territory.
Instead we verify the middleware's after_model() logic directly:
construct an AgentState dict with a synthetic AIMessage carrying
tool_calls, run after_model, and assert the result.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from deepagents import FilesystemPermission
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from quoriv.permissions.guard import (
    PathProtectionMiddleware,
    _check_denial,
    _denial_message,
    _extract_path,
)
from quoriv.permissions.paths import PATH_PROTECTION


def _state(messages: list[Any]) -> dict[str, Any]:
    """Minimal AgentState dict for testing."""
    return {"messages": messages}


def _runtime() -> Any:
    """A throwaway runtime; the middleware never touches it."""
    return MagicMock()


def _ai(tool_calls: list[dict[str, Any]]) -> AIMessage:
    return AIMessage(content="", tool_calls=tool_calls)


def _tool_call(name: str, args: dict[str, Any], call_id: str = "tc1") -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestCheckDenial:
    def test_matching_write_returns_rule(self) -> None:
        result = _check_denial(PATH_PROTECTION, "write", "/.env")
        assert result is not None
        assert result.mode == "deny"

    def test_matching_glob_pattern(self) -> None:
        result = _check_denial(PATH_PROTECTION, "write", "/.env.local")
        assert result is not None

    def test_nested_git_path_blocked(self) -> None:
        result = _check_denial(PATH_PROTECTION, "write", "/.git/refs/heads/main")
        assert result is not None

    def test_ssh_read_blocked(self) -> None:
        result = _check_denial(PATH_PROTECTION, "read", "/.ssh/id_rsa")
        assert result is not None

    def test_secrets_read_blocked(self) -> None:
        result = _check_denial(PATH_PROTECTION, "read", "/secrets/api_keys.json")
        assert result is not None

    def test_unrelated_path_allowed(self) -> None:
        assert _check_denial(PATH_PROTECTION, "write", "/src/main.py") is None

    def test_env_read_allowed(self) -> None:
        # Only WRITE is denied for /.env, not read.
        assert _check_denial(PATH_PROTECTION, "read", "/.env") is None

    def test_empty_rules_always_allows(self) -> None:
        assert _check_denial([], "write", "/.env") is None


class TestExtractPath:
    def test_file_path_key(self) -> None:
        assert _extract_path({"file_path": "/foo.py"}) == "/foo.py"

    def test_path_key_fallback(self) -> None:
        assert _extract_path({"path": "/bar.py"}) == "/bar.py"

    def test_file_path_wins_over_path(self) -> None:
        assert _extract_path({"file_path": "/a", "path": "/b"}) == "/a"

    def test_non_dict_returns_none(self) -> None:
        assert _extract_path("not a dict") is None
        assert _extract_path(None) is None

    def test_non_string_path_returns_none(self) -> None:
        assert _extract_path({"file_path": 42}) is None

    def test_missing_keys_returns_none(self) -> None:
        assert _extract_path({"other": "x"}) is None


class TestDenialMessage:
    def test_includes_path_and_operation(self) -> None:
        rule = FilesystemPermission(operations=["write"], paths=["/.env"], mode="deny")
        msg = _denial_message(rule, "/.env", "write")
        assert "/.env" in msg
        assert "write" in msg
        assert "denied" in msg


# ---------------------------------------------------------------------------
# Middleware behavior
# ---------------------------------------------------------------------------


class TestPathProtectionMiddleware:
    def test_no_messages_returns_none(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        assert mw.after_model(_state([]), _runtime()) is None

    def test_no_ai_message_returns_none(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        state = _state([HumanMessage(content="hi")])
        assert mw.after_model(state, _runtime()) is None

    def test_ai_without_tool_calls_returns_none(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        state = _state([AIMessage(content="hello world")])
        assert mw.after_model(state, _runtime()) is None

    def test_allowed_tool_call_passes_through(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        state = _state([_ai([_tool_call("write_file", {"file_path": "/safe.py"})])])
        assert mw.after_model(state, _runtime()) is None

    def test_denied_write_replaced_with_error(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        ai = _ai([_tool_call("write_file", {"file_path": "/.env"}, call_id="x1")])
        result = mw.after_model(_state([ai]), _runtime())

        assert result is not None
        messages = result["messages"]
        # First entry is the modified AIMessage with the denied call removed
        assert isinstance(messages[0], AIMessage)
        assert messages[0].tool_calls == []
        # Second entry is the synthetic error ToolMessage
        assert isinstance(messages[1], ToolMessage)
        assert messages[1].status == "error"
        assert messages[1].tool_call_id == "x1"
        assert "/.env" in str(messages[1].content)

    def test_denied_edit_replaced(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        ai = _ai(
            [
                _tool_call(
                    "edit_file",
                    {"file_path": "/.git/HEAD", "old_string": "x", "new_string": "y"},
                    call_id="x2",
                )
            ]
        )
        result = mw.after_model(_state([ai]), _runtime())

        assert result is not None
        assert result["messages"][0].tool_calls == []
        assert result["messages"][1].status == "error"

    def test_mixed_calls_only_denied_replaced(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        ai = _ai(
            [
                _tool_call("write_file", {"file_path": "/safe.py"}, call_id="ok"),
                _tool_call("write_file", {"file_path": "/.env"}, call_id="bad"),
                _tool_call("read_file", {"file_path": "/src/main.py"}, call_id="ok2"),
            ]
        )
        result = mw.after_model(_state([ai]), _runtime())

        assert result is not None
        kept = result["messages"][0].tool_calls
        assert len(kept) == 2
        assert {c["id"] for c in kept} == {"ok", "ok2"}
        # Exactly one error message for the bad call
        errors = [m for m in result["messages"][1:] if isinstance(m, ToolMessage)]
        assert len(errors) == 1
        assert errors[0].tool_call_id == "bad"

    def test_non_filesystem_tool_passes_through(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        # `execute` is shell, not in _TOOL_OPERATION map → not gated here
        # (shell command path protection is a Phase 2 concern; the model
        # could shell-out to `cat /.env`, which is why we still need HITL).
        state = _state([_ai([_tool_call("execute", {"command": "cat /.env"})])])
        assert mw.after_model(state, _runtime()) is None

    def test_missing_path_arg_passes_through(self) -> None:
        # A malformed write_file call without a path. The middleware
        # shouldn't crash — it lets the call through and lets DeepAgents
        # surface the validation error.
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        state = _state([_ai([_tool_call("write_file", {"content": "x"})])])
        assert mw.after_model(state, _runtime()) is None

    def test_rules_property_returns_copy(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        rules_view = mw.rules
        rules_view.clear()  # mutate the returned list
        # Internal rules unchanged
        assert len(mw.rules) == len(PATH_PROTECTION)

    async def test_async_hook_delegates(self) -> None:
        mw = PathProtectionMiddleware(PATH_PROTECTION)
        ai = _ai([_tool_call("write_file", {"file_path": "/.env"}, call_id="x")])
        result = await mw.aafter_model(_state([ai]), _runtime())
        assert result is not None
        assert result["messages"][0].tool_calls == []
