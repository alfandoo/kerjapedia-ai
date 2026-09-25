"""Lightweight application tracing for System Monitoring.

ContextVar-based spans correlate API → retrieval → generation with the same
`trace_id` carried in logs and persisted traces. RAG-internal detail
(rerank weights, context shaping, verifier internals) stays on
`/admin/observability` per the boundary rule: here spans measure service
latency, dependency latency, errors, timeouts, and bottlenecks only.

Write policy (`maybe_persist_trace`): errors, timeouts, slow (>2s), and a 5%
sample — never every request, so the table stays bounded alongside the 7-day
retention.
"""

from __future__ import annotations

import logging
import random
import time
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

logger = logging.getLogger("kerjapedia.system")

_current_trace: ContextVar[dict[str, Any] | None] = ContextVar(
    "kerjapedia_system_trace", default=None
)

SLOW_TRACE_MS = 2000.0
TRACE_SAMPLE_RATE = 0.05


def start_trace(trace_id: str, route: str) -> dict[str, Any]:
    trace = {
        "trace_id": trace_id,
        "route": route,
        "started_at": time.perf_counter(),
        "spans": [],
        "stack": [],
    }
    _current_trace.set(trace)
    return trace


def get_trace_id() -> str | None:
    trace = _current_trace.get()
    return trace["trace_id"] if trace else None


def start_span(name: str, service: str) -> None:
    trace = _current_trace.get()
    if trace is None:
        return
    span_id = uuid4().hex[:12]
    parent = trace["stack"][-1]["span_id"] if trace["stack"] else None
    span = {
        "span_id": span_id,
        "parent_span_id": parent,
        "name": name,
        "service": service,
        "started_offset_ms": round((time.perf_counter() - trace["started_at"]) * 1000, 1),
        "duration_ms": None,
        "status": "running",
    }
    trace["stack"].append(span)
    trace["spans"].append(span)


def end_span(status: str = "ok", error: str | None = None) -> None:
    trace = _current_trace.get()
    if trace is None or not trace["stack"]:
        return
    span = trace["stack"].pop()
    elapsed = (time.perf_counter() - trace["started_at"]) * 1000.0
    span["duration_ms"] = round(elapsed - span["started_offset_ms"], 1)
    span["status"] = status
    if error:
        span["error"] = str(error)[:300]


def finish_trace(status: str = "ok") -> dict[str, Any] | None:
    trace = _current_trace.get()
    _current_trace.set(None)
    if trace is None:
        return None
    while trace["stack"]:
        end_span(status="aborted")
    duration_ms = round((time.perf_counter() - trace["started_at"]) * 1000.0, 1)
    return {
        "trace_id": trace["trace_id"],
        "route": trace["route"],
        "duration_ms": duration_ms,
        "status": status,
        "spans": trace["spans"],
    }


def should_persist(status: str, duration_ms: float) -> bool:
    if status in ("error", "timeout"):
        return True
    if duration_ms >= SLOW_TRACE_MS:
        return True
    return random.random() < TRACE_SAMPLE_RATE


def maybe_persist_trace(finished: dict[str, Any] | None) -> None:
    """Persist per policy; fail-safe, never raises."""
    if not finished:
        return
    if not should_persist(finished["status"], finished["duration_ms"]):
        return
    try:
        from datetime import UTC, datetime

        from app.db.session import create_session
        from app.models.business import RequestTrace

        with create_session() as session:
            if session.get(RequestTrace, finished["trace_id"]) is not None:
                return
            session.add(
                RequestTrace(
                    trace_id=finished["trace_id"],
                    route=finished["route"][:160],
                    started_at=datetime.now(UTC),
                    duration_ms=finished["duration_ms"],
                    status=finished["status"][:20],
                    span_count=len(finished["spans"]),
                    spans=finished["spans"],
                )
            )
            session.commit()
    except Exception:
        logger.debug("trace persist skipped", exc_info=True)
