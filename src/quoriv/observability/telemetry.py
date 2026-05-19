"""Optional outbound telemetry — Phase 4 Slice 1.

Off by default. This module establishes the **surface** Quoriv will
use to report usage events once a concrete backend is wired —
:func:`is_enabled` is the gating check every emitter must call, and
:func:`report` is a stub that no-ops today.

Design contract:

* **Opt-in, always.** ``TelemetryConfig.enabled`` defaults to
  ``False``. We never transmit anything unless the user explicitly
  flipped the flag in ``config.toml`` (or any future `quoriv
  telemetry enable` CLI command).
* **No-op until a backend ships.** ``report()`` accepts events but
  drops them on the floor (at debug-level log) regardless of the
  flag's value. Users who opt in now won't see traffic; the
  contract is "your opt-in is captured and respected; nothing
  transmits yet". When the backend lands, the gating check is
  already in place at every call site.
* **No PII**. The event name + a small set of structured fields
  are all that future reports will carry. Free-text fields (prompt
  bodies, code samples, file paths) are out of scope.

Future shape — when a backend lands the implementation of
``report()`` becomes something like::

    if is_enabled(config):
        _client.capture(event=event_name, properties=kwargs)

…and nothing else in Quoriv needs to change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from quoriv.config.schema import QuorivConfig, TelemetryConfig


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


def report(
    event_name: str,
    config: QuorivConfig | TelemetryConfig | None = None,
    **fields: Any,
) -> None:
    """Record one telemetry event.

    Today this only logs at debug level — the network sink ships in
    a follow-up. Callers should still pass a real ``config`` so the
    gating check works out of the box once the backend lands.

    Args:
        event_name: Short event identifier (e.g. ``"chat.start"``,
            ``"tool.execute"``).
        config: Loaded Quoriv configuration or a bare
            :class:`TelemetryConfig`. ``None`` short-circuits — no
            report, no log.
        **fields: Structured event payload. Must not contain PII
            (no prompts, code samples, or filesystem paths beyond
            short labels). The future backend will drop unexpected
            keys at the sink layer too.
    """
    if not is_enabled(config):
        return
    # Backend-less stub: write to the loguru sink the rest of Quoriv
    # uses for debug breadcrumbs. Real sink lands later.
    logger.debug("telemetry event {!r} fields={}", event_name, fields)
