"""Tests for ``quoriv.observability.telemetry`` — Phase 4 Slice 1 + Slice 6."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from quoriv.config.schema import QuorivConfig, TelemetryConfig
from quoriv.observability import telemetry as telemetry_mod
from quoriv.observability.telemetry import _build_envelope, is_enabled, report


class TestTelemetryConfigDefaults:
    def test_disabled_by_default(self) -> None:
        # The whole point: opt-in, always. A bare default config
        # must report telemetry as OFF.
        assert TelemetryConfig().enabled is False

    def test_endpoint_defaults_to_none(self) -> None:
        assert TelemetryConfig().endpoint is None

    def test_quoriv_config_exposes_telemetry_section(self) -> None:
        config = QuorivConfig.model_validate({})
        assert config.telemetry.enabled is False
        assert config.telemetry.endpoint is None

    def test_explicit_opt_in_round_trips(self) -> None:
        config = QuorivConfig.model_validate(
            {"telemetry": {"enabled": True, "endpoint": "https://telemetry.example/v1"}}
        )
        assert config.telemetry.enabled is True
        assert config.telemetry.endpoint == "https://telemetry.example/v1"

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TelemetryConfig.model_validate({"enabled": False, "secret_field": "x"})


class TestIsEnabled:
    def test_none_config_is_disabled(self) -> None:
        assert is_enabled(None) is False

    def test_default_config_is_disabled(self) -> None:
        assert is_enabled(QuorivConfig.model_validate({})) is False

    def test_opted_in_config_is_enabled(self) -> None:
        config = QuorivConfig.model_validate({"telemetry": {"enabled": True}})
        assert is_enabled(config) is True

    def test_accepts_bare_telemetry_section(self) -> None:
        # Callers that already drilled down to the leaf shouldn't
        # have to wrap it in QuorivConfig.
        assert is_enabled(TelemetryConfig(enabled=True)) is True
        assert is_enabled(TelemetryConfig(enabled=False)) is False


class TestReport:
    def test_disabled_config_is_noop(self, caplog: pytest.LogCaptureFixture) -> None:
        # No-op = no log line even at debug.
        config = QuorivConfig.model_validate({})
        report("chat.start", config=config, model="openai:gpt-4")
        # caplog defaults at WARNING; at debug level there'd still
        # be nothing because the function short-circuits early.
        assert "chat.start" not in caplog.text

    def test_none_config_is_noop(self) -> None:
        # No exception, no traffic, just a silent skip.
        report("chat.start", config=None)

    def test_enabled_config_does_not_raise(self) -> None:
        # Today the enabled path logs at debug. We only assert it
        # doesn't blow up — the loguru sink isn't pytest's caplog
        # so checking the actual log text would be implementation-
        # coupled and fragile.
        config = QuorivConfig.model_validate({"telemetry": {"enabled": True}})
        report("chat.start", config=config, model="anthropic:claude-sonnet-4")

    def test_kwargs_accepted(self) -> None:
        # Smoke check that arbitrary structured fields flow through
        # without raising — the future backend will do its own
        # validation at the sink.
        report(
            "tool.execute",
            config=TelemetryConfig(enabled=True),
            tool_name="execute",
            duration_ms=42,
            success=True,
        )


# ---------------------------------------------------------------------------
# Backend transport — Phase 4 Slice 6
# ---------------------------------------------------------------------------


class _PostRecorder:
    """Captures httpx.post calls for assertion without doing real I/O."""

    def __init__(self, *, status: int = 200, raise_exc: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._status = status
        self._raise_exc = raise_exc

    def __call__(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        if self._raise_exc is not None:
            raise self._raise_exc
        return httpx.Response(status_code=self._status, request=httpx.Request("POST", url))


class TestApiKeyField:
    def test_api_key_default_none(self) -> None:
        assert TelemetryConfig().api_key is None

    def test_api_key_round_trips(self) -> None:
        config = TelemetryConfig.model_validate(
            {"enabled": True, "endpoint": "https://x", "api_key": "ph_secret"}
        )
        assert config.api_key == "ph_secret"


class TestBuildEnvelope:
    def test_includes_event_name_and_fields(self) -> None:
        env = _build_envelope("chat.start", {"model": "openai:gpt-4o"})
        assert env["event"] == "chat.start"
        assert env["fields"] == {"model": "openai:gpt-4o"}

    def test_client_metadata_present(self) -> None:
        env = _build_envelope("x", {})
        client = env["client"]
        assert client["name"] == "quoriv"
        assert "version" in client
        assert "platform" in client
        assert "python" in client

    def test_timestamp_is_iso_utc(self) -> None:
        env = _build_envelope("x", {})
        # ISO-8601 UTC strings end with +00:00 (or Z, but datetime
        # uses +00:00 with timezone.utc).
        assert env["timestamp"].endswith("+00:00")

    def test_envelope_is_serialisable(self) -> None:
        # Must round-trip through httpx's json= encoder.
        env = _build_envelope("evt", {"a": 1, "b": "two"})
        # If this raises, downstream httpx.post(json=...) would too.
        json.dumps(env)


class TestReportTransport:
    @pytest.fixture
    def recorder(self, monkeypatch: pytest.MonkeyPatch) -> _PostRecorder:
        rec = _PostRecorder()
        monkeypatch.setattr(telemetry_mod.httpx, "post", rec)
        return rec

    def test_no_endpoint_skips_http_post(self, recorder: _PostRecorder) -> None:
        # Enabled but no endpoint configured — still must not call the
        # network. The log breadcrumb is implementation detail.
        config = TelemetryConfig(enabled=True, endpoint=None)
        report("chat.start", config=config)
        assert recorder.calls == []

    def test_disabled_skips_http_post(self, recorder: _PostRecorder) -> None:
        config = TelemetryConfig(enabled=False, endpoint="https://sink.example/cap")
        report("chat.start", config=config)
        assert recorder.calls == []

    def test_enabled_with_endpoint_posts_envelope(self, recorder: _PostRecorder) -> None:
        config = TelemetryConfig(enabled=True, endpoint="https://sink.example/cap")
        report("chat.start", config=config, model="openai:gpt-4o")

        assert len(recorder.calls) == 1
        call = recorder.calls[0]
        assert call["url"] == "https://sink.example/cap"
        body = call["json"]
        assert body["event"] == "chat.start"
        assert body["fields"] == {"model": "openai:gpt-4o"}
        assert body["client"]["name"] == "quoriv"
        # Content-Type is set explicitly so a sink can content-negotiate.
        assert call["headers"]["Content-Type"] == "application/json"
        # Authorization absent when no api_key set.
        assert "Authorization" not in call["headers"]

    def test_api_key_added_as_bearer_header(self, recorder: _PostRecorder) -> None:
        config = TelemetryConfig(
            enabled=True,
            endpoint="https://sink.example/cap",
            api_key="ph_writeKEY",
        )
        report("evt", config=config)
        call = recorder.calls[0]
        assert call["headers"]["Authorization"] == "Bearer ph_writeKEY"

    def test_uses_short_timeout(self, recorder: _PostRecorder) -> None:
        # A misbehaving sink must never stall the agent.
        config = TelemetryConfig(enabled=True, endpoint="https://sink.example/cap")
        report("evt", config=config)
        assert recorder.calls[0]["timeout"] == telemetry_mod._DEFAULT_TIMEOUT
        assert telemetry_mod._DEFAULT_TIMEOUT <= 5.0

    def test_httpx_exception_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Network errors must NEVER raise out of report().
        rec = _PostRecorder(raise_exc=httpx.ConnectError("boom"))
        monkeypatch.setattr(telemetry_mod.httpx, "post", rec)
        config = TelemetryConfig(enabled=True, endpoint="https://sink.example/cap")
        report("evt", config=config)  # Must not raise.
        assert len(rec.calls) == 1

    def test_non_2xx_response_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Sinks that return 5xx / 4xx must be tolerated silently.
        rec = _PostRecorder(status=500)
        monkeypatch.setattr(telemetry_mod.httpx, "post", rec)
        config = TelemetryConfig(enabled=True, endpoint="https://sink.example/cap")
        report("evt", config=config)
        assert len(rec.calls) == 1

    def test_bare_telemetry_config_accepted(self, recorder: _PostRecorder) -> None:
        # Callers that already drilled to the leaf shouldn't need to
        # wrap in QuorivConfig.
        config = TelemetryConfig(enabled=True, endpoint="https://sink.example/cap")
        report("evt", config=config, key="value")
        assert recorder.calls[0]["json"]["fields"] == {"key": "value"}
