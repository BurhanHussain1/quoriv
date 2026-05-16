"""Observability: logging, cost accounting, traces, optional telemetry.

Modules:
    log         loguru-based structured logging.
    cost        Per-call token and dollar cost accounting.
    trace       Slice 9 — JSONL trace log per chat thread
                (:class:`TraceLogger`). Drives the ``/cost`` slash command.
    telemetry   Optional outbound telemetry. Disabled unless explicitly opted in.
"""

from __future__ import annotations

from quoriv.observability.trace import TraceLogger

__all__ = [
    "TraceLogger",
]
