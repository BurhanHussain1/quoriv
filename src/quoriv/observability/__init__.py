"""Observability: logging, cost accounting, traces, optional telemetry.

Modules:
    log         loguru-based structured logging.
    cost        Slice 9c — per-provider USD/1k-token rate table
                (:data:`RATES`), :func:`lookup_rate`, :func:`estimate_cost`.
    trace       Slice 9 — JSONL trace log per chat thread
                (:class:`TraceLogger`). Drives the ``/cost`` slash command.
    telemetry   Optional outbound telemetry. Disabled unless explicitly opted in.
"""

from __future__ import annotations

from quoriv.observability.cost import (
    RATES,
    ProviderRate,
    effective_rates,
    estimate_cost,
    lookup_rate,
)
from quoriv.observability.trace import TraceLogger

__all__ = [
    "RATES",
    "ProviderRate",
    "TraceLogger",
    "effective_rates",
    "estimate_cost",
    "lookup_rate",
]
