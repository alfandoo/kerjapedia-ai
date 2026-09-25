"""Structured logging — JSON in production, human-readable in development.

Minimal fields per record: timestamp, level, service, request_id, route,
latency, outcome, error_type. Sensitive values (tokens, keys, raw CV, PII)
must never be logged; use the redaction helpers in answering.guardrails
before attaching payloads.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class _JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "route", "latency_ms", "outcome", "error_type"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(service: str, app_env: str) -> None:
    """Configure root logging once; safe to call multiple times."""
    root = logging.getLogger()
    if getattr(root, "_kerjapedia_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    if app_env.lower() == "production":
        handler.setFormatter(_JsonFormatter(service))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root._kerjapedia_configured = True  # type: ignore[attr-defined]


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    request_id: str | None = None,
    route: str | None = None,
    latency_ms: int | None = None,
    outcome: str | None = None,
    error_type: str | None = None,
) -> None:
    extra = {
        k: v
        for k, v in {
            "request_id": request_id,
            "route": route,
            "latency_ms": latency_ms,
            "outcome": outcome,
            "error_type": error_type,
        }.items()
        if v is not None
    }
    logger.log(level, message, extra=extra)
