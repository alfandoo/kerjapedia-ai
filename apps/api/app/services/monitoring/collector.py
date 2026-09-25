"""Fail-safe collection for System Monitoring.

Every writer here swallows its own errors: monitoring must never break the
main application (§16). Latency histograms use fixed millisecond buckets so
p50/p95/p99 can be approximated from aggregates without per-request rows.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

logger = logging.getLogger("kerjapedia.system")

PROCESS_STARTED_AT = datetime.now(UTC)

# Fixed histogram buckets (ms, upper bounds); last bucket is +Inf overflow.
LATENCY_HISTOGRAM_BOUNDS_MS: tuple[int, ...] = (50, 100, 250, 500, 1000, 2000, 5000, 15000)

BUCKET_RETENTION_DAYS = 7
PROBE_RETENTION_DAYS = 7
LOG_RETENTION_DAYS = 7
TRACE_RETENTION_DAYS = 7
ALERT_RETENTION_DAYS = 30


def process_uptime_seconds() -> float:
    return max(0.0, (datetime.now(UTC) - PROCESS_STARTED_AT).total_seconds())


def empty_histogram() -> dict[str, int]:
    return {str(bound): 0 for bound in LATENCY_HISTOGRAM_BOUNDS_MS} | {"+Inf": 0}


def record_histogram_value(histogram: dict[str, int], latency_ms: float) -> None:
    for bound in LATENCY_HISTOGRAM_BOUNDS_MS:
        if latency_ms <= bound:
            histogram[str(bound)] = int(histogram.get(str(bound), 0)) + 1
            return
    histogram["+Inf"] = int(histogram.get("+Inf", 0)) + 1


def merge_histograms(histograms: list[dict]) -> dict[str, int]:
    merged = empty_histogram()
    for histogram in histograms or []:
        for key, value in (histogram or {}).items():
            merged[key] = int(merged.get(key, 0)) + int(value or 0)
    return merged


def histogram_percentile(histogram: dict, total: int, quantile: float) -> float | None:
    """Approximate percentile from fixed buckets (upper-bound interpolation)."""
    if not total:
        return None
    rank = max(1, min(total, int(total * quantile) + (1 if total * quantile % 1 else 0)))
    cumulative = 0
    previous = 0.0
    for bound in [*LATENCY_HISTOGRAM_BOUNDS_MS, None]:
        key = str(bound) if bound is not None else "+Inf"
        cumulative += int((histogram or {}).get(key, 0))
        if cumulative >= rank:
            upper = float(bound) if bound is not None else previous * 2.0 or 15000.0
            return round((previous + upper) / 2.0, 1)
        previous = float(bound) if bound is not None else previous
    return None


def classify_error(status_code: int | None, error_code: str | None = None) -> str:
    """Map HTTP outcome to an operational error class (no PII involved)."""
    code = (error_code or "").lower()
    if "timeout" in code:
        return "timeout"
    if status_code == 429 or "rate_limit" in code:
        return "rate_limited"
    if status_code == 503 and "rag_" in code:
        return "provider"
    if status_code is None:
        return "unknown"
    if 400 <= status_code < 500:
        if status_code in (401, 403):
            return "auth"
        return "validation" if status_code in (400, 404, 422) else "client"
    if status_code >= 500:
        return "server"
    return "ok"


def route_template(request) -> str:
    """Low-cardinality route label: template when matched, else raw path."""
    try:
        route = request.scope.get("route")
        path = getattr(route, "path", None)
        if path:
            return str(path)[:160]
    except Exception:
        pass
    try:
        return str(request.url.path)[:160]
    except Exception:
        return "unknown"


def _minute_bucket(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


def record_http_request(
    *,
    route: str,
    method: str,
    status_code: int,
    latency_ms: int,
    error_type: str | None = None,
) -> None:
    """Upsert one per-minute aggregate; fail-safe, never raises."""
    try:
        from app.db.session import create_session
        from app.models.business import HttpRequestBucket

        status_class = f"{status_code // 100}xx" if status_code else "unknown"
        error = classify_error(status_code, error_type)
        with create_session() as session:
            row = session.get(
                HttpRequestBucket,
                {
                    "bucket": _minute_bucket(datetime.now(UTC)),
                    "route": route[:160],
                    "method": method[:10],
                    "status_class": status_class,
                },
            )
            if row is None:
                row = HttpRequestBucket(
                    bucket=_minute_bucket(datetime.now(UTC)),
                    route=route[:160],
                    method=method[:10],
                    status_class=status_class,
                    count=0,
                    error_count=0,
                    sum_latency_ms=0,
                    latency_histogram=empty_histogram(),
                )
                session.add(row)
            row.count = int(row.count or 0) + 1
            if error not in ("ok",):
                row.error_count = int(row.error_count or 0) + 1
            row.sum_latency_ms = int(row.sum_latency_ms or 0) + max(0, int(latency_ms))
            histogram = dict(row.latency_histogram or {})
            record_histogram_value(histogram, max(0.0, float(latency_ms)))
            row.latency_histogram = histogram
            session.commit()
    except Exception:
        logger.debug("http bucket write skipped", exc_info=True)


def record_rate_limited(*, route: str) -> None:
    """Count one 429 in a synthetic bucket for spike detection (fail-safe)."""
    try:
        from app.db.session import create_session
        from app.models.business import HttpRequestBucket

        bucket = _minute_bucket(datetime.now(UTC))
        with create_session() as session:
            row = session.get(
                HttpRequestBucket,
                {
                    "bucket": bucket,
                    "route": "__rate_limited__",
                    "method": "ANY",
                    "status_class": "4xx",
                },
            )
            if row is None:
                row = HttpRequestBucket(
                    bucket=bucket,
                    route="__rate_limited__",
                    method="ANY",
                    status_class="4xx",
                    count=0,
                    error_count=0,
                    sum_latency_ms=0,
                    latency_histogram=empty_histogram(),
                )
                session.add(row)
            row.count = int(row.count or 0) + 1
            row.error_count = int(row.error_count or 0) + 1
            session.commit()
    except Exception:
        logger.debug("rate-limit bucket write skipped", exc_info=True)


def persist_request_observation(
    *,
    route: str,
    method: str,
    status_code: int,
    latency_ms: int,
    error_type: str | None,
    request_id: str,
    trace_id: str,
    finished_trace: dict | None = None,
) -> None:
    """One fail-safe call per request: bucket + conditional log + trace."""
    record_http_request(
        route=route,
        method=method,
        status_code=status_code,
        latency_ms=latency_ms,
        error_type=error_type,
    )
    error = classify_error(status_code, error_type)
    if error in ("timeout", "provider", "server") or status_code >= 500:
        write_system_log(
            level="error",
            service="api",
            message=f"{method} {route} -> {status_code} ({error})",
            request_id=request_id,
            trace_id=trace_id,
            route=route,
            status_code=status_code,
            duration_ms=max(0, int(latency_ms)),
            error_type=error if error != "ok" else None,
        )
    if finished_trace is not None:
        from app.services.monitoring.tracing import maybe_persist_trace

        maybe_persist_trace(finished_trace)


def write_system_log(
    *,
    level: str,
    service: str,
    message: str,
    request_id: str | None = None,
    trace_id: str | None = None,
    route: str | None = None,
    status_code: int | None = None,
    duration_ms: int | None = None,
    error_type: str | None = None,
) -> None:
    """Persist warn/error entries only; info/debug stay on stdout (volume)."""
    if level not in ("warn", "error"):
        return
    try:
        from app.api.state import now_utc
        from app.db.session import create_session
        from app.models.business import SystemLog

        with create_session() as session:
            session.add(
                SystemLog(
                    log_id=f"log_{uuid4().hex}",
                    level=level,
                    service=service[:80],
                    message=message[:2000],
                    request_id=request_id,
                    trace_id=trace_id,
                    route=route[:160] if route else None,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    error_type=error_type[:80] if error_type else None,
                    created_at=now_utc(),
                )
            )
            session.commit()
    except Exception:
        logger.debug("system log write skipped", exc_info=True)


def record_dependency_probe(
    *, service: str, status: str, latency_ms: float | None, error: str | None
) -> None:
    try:
        from app.api.state import now_utc
        from app.db.session import create_session
        from app.models.business import DependencyProbe

        with create_session() as session:
            session.add(
                DependencyProbe(
                    service=service[:80],
                    status=status,
                    latency_ms=latency_ms,
                    error=(error[:500] if error else None),
                    checked_at=now_utc(),
                )
            )
            session.commit()
    except Exception:
        logger.debug("probe write skipped", exc_info=True)


def cleanup_monitoring() -> dict[str, int]:
    """Delete expired monitoring rows; returns per-table counts."""
    from sqlalchemy import text

    from app.db.session import create_session

    now = datetime.now(UTC)
    cuts = {
        "http_request_buckets": (now - timedelta(days=BUCKET_RETENTION_DAYS), "bucket"),
        "dependency_probes": (now - timedelta(days=PROBE_RETENTION_DAYS), "checked_at"),
        "system_logs": (now - timedelta(days=LOG_RETENTION_DAYS), "created_at"),
        "request_traces": (now - timedelta(days=TRACE_RETENTION_DAYS), "started_at"),
        "alert_events": (now - timedelta(days=ALERT_RETENTION_DAYS), "created_at"),
    }
    counts: dict[str, int] = {}
    try:
        with create_session() as session:
            for table, (cutoff, column) in cuts.items():
                result = session.execute(
                    text(f"DELETE FROM {table} WHERE {column} < :cutoff"),
                    {"cutoff": cutoff},
                )
                counts[table] = int(result.rowcount or 0)
            session.commit()
    except Exception:
        logger.debug("monitoring cleanup skipped", exc_info=True)
    return counts
