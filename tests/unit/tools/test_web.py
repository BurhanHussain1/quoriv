"""Tests for ``quoriv.tools.web`` — Phase 3 Slice 6.

The ``web_fetch`` tool wraps ``httpx.Client.get``. We monkeypatch
``httpx.Client`` to keep the test suite hermetic — no real network
calls during ``pytest``. The patched client lets each test pin the
response (status, headers, body) and assert how the tool maps those
to its returned dict.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from quoriv.tools import QUORIV_TOOLS
from quoriv.tools.web import _DEFAULT_MAX_CHARS, web_fetch


class _FakeResponse:
    """Minimal stand-in for ``httpx.Response`` — exposes only the
    attributes ``web_fetch`` actually reads."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        content_type: str | None = "text/html; charset=utf-8",
        url: str = "https://example.com",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type} if content_type else {}
        self.url = url


class _FakeClient:
    """Captures the URL and returns a canned response."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_url: str | None = None

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def get(self, url: str) -> _FakeResponse:
        self.last_url = url
        return self._response


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> _FakeClient:
    """Replace ``httpx.Client`` with a fake that returns ``response``."""
    client = _FakeClient(response)
    monkeypatch.setattr(
        "quoriv.tools.web.httpx.Client",
        lambda **_kwargs: client,
    )
    return client


# ---------------------------------------------------------------------------
# Happy path — small body returned intact
# ---------------------------------------------------------------------------


class TestWebFetchHappyPath:
    def test_returns_dict_with_expected_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_httpx(monkeypatch, _FakeResponse(text="hello"))
        result = web_fetch.invoke({"url": "https://example.com"})
        assert isinstance(result, dict)
        assert set(result) >= {
            "status_code",
            "content_type",
            "text",
            "truncated",
            "url",
        }

    def test_short_body_is_not_truncated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = "small page body"
        _patch_httpx(monkeypatch, _FakeResponse(text=body))
        result = web_fetch.invoke({"url": "https://example.com"})
        assert result["text"] == body
        assert result["truncated"] is False

    def test_status_and_content_type_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_httpx(
            monkeypatch,
            _FakeResponse(
                status_code=201,
                text="ok",
                content_type="application/json",
            ),
        )
        result = web_fetch.invoke({"url": "https://example.com"})
        assert result["status_code"] == 201
        assert result["content_type"] == "application/json"

    def test_url_request_forwarded_to_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _patch_httpx(monkeypatch, _FakeResponse(text="x"))
        web_fetch.invoke({"url": "https://example.com/path?q=1"})
        assert client.last_url == "https://example.com/path?q=1"


# ---------------------------------------------------------------------------
# Truncation — the soft cap keeps a megabyte page from blowing the window
# ---------------------------------------------------------------------------


class TestTruncation:
    def test_body_truncated_to_max_chars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two characters past the cap so the truncation message can
        # report ``+2 chars``.
        cap = 50
        body = "x" * (cap + 2)
        _patch_httpx(monkeypatch, _FakeResponse(text=body))
        result = web_fetch.invoke({"url": "https://example.com", "max_chars": cap})
        assert result["truncated"] is True
        assert result["text"].startswith("x" * cap)
        assert "(truncated, +2 chars)" in result["text"]

    def test_body_at_exact_cap_not_truncated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cap = 100
        body = "y" * cap
        _patch_httpx(monkeypatch, _FakeResponse(text=body))
        result = web_fetch.invoke({"url": "https://example.com", "max_chars": cap})
        assert result["truncated"] is False
        assert result["text"] == body

    def test_default_max_chars_applies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = "z" * (_DEFAULT_MAX_CHARS + 1)
        _patch_httpx(monkeypatch, _FakeResponse(text=body))
        result = web_fetch.invoke({"url": "https://example.com"})
        assert result["truncated"] is True


# ---------------------------------------------------------------------------
# Error handling — network failure / DNS / timeout
# ---------------------------------------------------------------------------


class TestNetworkFailure:
    def test_http_error_returns_error_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Make the ``Client`` constructor raise an HTTPError to
        # simulate a connect failure. The tool catches it and
        # converts to a structured error dict.
        class _Boom:
            def __enter__(self) -> _Boom:
                return self

            def __exit__(self, *exc: Any) -> None:
                return None

            def get(self, _url: str) -> Any:
                raise httpx.ConnectError("simulated DNS failure")

        monkeypatch.setattr(
            "quoriv.tools.web.httpx.Client",
            lambda **_kwargs: _Boom(),
        )
        result = web_fetch.invoke({"url": "https://nowhere.invalid"})
        assert "error" in result
        assert "HTTP error" in result["error"]
        assert "simulated DNS failure" in result["error"]
        # No text / status fields when erroring.
        assert "text" not in result
        assert result["url"] == "https://nowhere.invalid"

    def test_timeout_returns_error_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ``ReadTimeout`` is a subclass of ``HTTPError`` so it goes
        # through the same defensive branch.
        class _Slow:
            def __enter__(self) -> _Slow:
                return self

            def __exit__(self, *exc: Any) -> None:
                return None

            def get(self, _url: str) -> Any:
                raise httpx.ReadTimeout("simulated read timeout")

        monkeypatch.setattr(
            "quoriv.tools.web.httpx.Client",
            lambda **_kwargs: _Slow(),
        )
        result = web_fetch.invoke({"url": "https://slow.example"})
        assert "error" in result
        assert "simulated read timeout" in result["error"]


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


class TestToolSurface:
    def test_registered_in_quoriv_tools(self) -> None:
        # Smoke check that the agent will see this tool.
        names = [t.name for t in QUORIV_TOOLS]
        assert "web_fetch" in names

    def test_has_useful_description(self) -> None:
        # Docstring becomes the tool description the model sees.
        desc = (web_fetch.description or "").lower()
        # We don't pin exact wording but it has to mention the verb
        # so the model can route to it.
        assert "fetch" in desc
        assert "url" in desc
