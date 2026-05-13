"""Observability: logging, cost accounting, traces, optional telemetry.

Modules:
    log         loguru-based structured logging.
    cost        Per-call token and dollar cost accounting.
    trace       Local JSON trace export (every tool call, every model call).
    telemetry   Optional outbound telemetry. Disabled unless explicitly opted in.
"""
