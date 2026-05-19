"""Tests for ``quoriv.observability.telemetry`` — Phase 4 Slice 1."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quoriv.config.schema import QuorivConfig, TelemetryConfig
from quoriv.observability.telemetry import is_enabled, report


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
