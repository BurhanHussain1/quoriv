"""Optional outbound telemetry — Phase 4 Slice 1 + Slice 6.

Off by default. When the user opts in **and** configures an
``endpoint``, :func:`report` POSTs a JSON envelope describing the
event to that URL via HTTP. Any sink that accepts JSON works —
PostHog's ``/capture/`` endpoint, a self-hosted FastAPI receiver, a
cloud function. There is no hard dependency on a specific provider.

Design contract:

* **Opt-in, always.** ``TelemetryConfig.enabled`` defaults to
  ``False``. We never transmit anything unless the user explicitly
  flipped the flag in ``config.toml``.
* **No endpoint, no traffic.** Even with ``enabled=True``, if
  ``endpoint`` is ``None`` we only emit a debug log — no network
  call.
* **Never break the agent.** Every transport error is caught and
  logged at debug. The worst case is one HTTP timeout per event;
  the request budget is ``_DEFAULT_TIMEOUT`` seconds.
* **No PII**. The event name + a small set of structured fields
  are all reports carry. Free-text fields (prompt bodies, code
  samples, file paths beyond short labels) are out of scope.

Envelope shape::

    {
      "event": "chat.start",
      "fields": { ... caller-supplied kwargs ... },
      "client": {
        "name": "quoriv",
        "version": "<__version__>",
        "platform": "<sys.platform>",
        "python": "<major.minor>"
      },
      "timestamp": "<ISO-8601 UTC>"
    }

When ``api_key`` is set on the config, it is forwarded as
``Authorization: Bearer <api_key>`` so self-hosted sinks can
distinguish clients.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger

from quoriv import __version__

if TYPE_CHECKING:
    from quoriv.config.schema import QuorivConfig, TelemetryConfig


# Short by design: a misbehaving sink must not stall the agent. Two
# seconds is enough for the happy path on most clouds while keeping
# the worst case bounded.
_DEFAULT_TIMEOUT: float = 2.0


def is_enabled(config: QuorivConfig | TelemetryConfig | None) -> bool:
    """Return ``True`` only when telemetry is explicitly opted in.

    Accepts either a full :class:`QuorivConfig` (the common chat-loop
    case) or a bare :class:`TelemetryConfig` (for callers that
    already drilled down). ``None`` always returns ``False`` so
    legacy code paths without config plumbing stay silent.
    """
    if config is None:
        return False
    # Duck-type: anything with a ``.telemetry`` attribute is a
    # QuorivConfig; anything with a ``.enabled`` is the leaf.
    telemetry = getattr(config, "telemetry", config)
    return bool(getattr(telemetry, "enabled", False))


def _resolve_telemetry(config: QuorivConfig | TelemetryConfig | None) -> Any:
    """Return the bare ``TelemetryConfig`` from either container shape."""
    if config is None:
        return None
    return getattr(config, "telemetry", config)


def _build_envelope(event_name: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Construct the JSON payload sent to the telemetry sink.

    Pure: no side effects, no I/O. ``timestamp`` is taken from
    :func:`datetime.now(timezone.utc)`. Caller-supplied ``fields`` are
    passed through verbatim — the sink is responsible for filtering
    or rejecting keys it doesn't recognise.
    """
    return {
        "event": event_name,
        "fields": dict(fields),
        "client": {
            "name": "quoriv",
            "version": __version__,
            "platform": sys.platform,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


def report(
    event_name: str,
    config: QuorivConfig | TelemetryConfig | None = None,
    **fields: Any,
) -> None:
    """Record one telemetry event.

    When ``config`` is opted in and carries an ``endpoint``, POSTs a
    JSON envelope (see module docstring) to that URL. Otherwise emits
    a debug log only and returns. All transport errors are caught
    and logged at debug — telemetry never raises out of this call.

    Args:
        event_name: Short event identifier (e.g. ``"chat.start"``,
            ``"tool.execute"``).
        config: Loaded Quoriv configuration or a bare
            :class:`TelemetryConfig`. ``None`` short-circuits — no
            report, no log.
        **fields: Structured event payload. Must not contain PII.
    """
    if not is_enabled(config):
        return

    telemetry = _resolve_telemetry(config)
    endpoint: str | None = getattr(telemetry, "endpoint", None)
    api_key: str | None = getattr(telemetry, "api_key", None)

    if endpoint is None:
        # Enabled but no sink configured — still log a breadcrumb so
        # the user can confirm the opt-in plumbing reached this call.
        logger.debug("telemetry event {!r} fields={} (no endpoint configured)", event_name, fields)
        return

    payload = _build_envelope(event_name, fields)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = httpx.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=_DEFAULT_TIMEOUT,
        )
        # Sink should return 2xx; non-2xx is logged but never raised
        # so a misconfigured endpoint doesn't break the agent.
        if response.status_code >= 400:
            logger.debug(
                "telemetry sink returned {} for event {!r}",
                response.status_code,
                event_name,
            )
    except Exception as exc:
        logger.debug("telemetry POST failed for event {!r}: {}", event_name, exc)
