"""System Monitoring endpoints (`/admin/system/*`) — admin only.

Separate from RAG observability (`/admin/observability` + `/admin/metrics`):
this surface watches application/API health, request performance, dependency
latency, logs, traces, and alerts. It never reports RAG quality (recall,
faithfulness, retrieval analysis, tokens, cost).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func

from app.api.dependencies import AdminUser, DbSession
from app.api.pagination import apply_db_pagination
from app.models.business import (
    AlertEvent,
    DependencyProbe,
    HttpRequestBucket,
    RequestTrace,
    SystemLog,
)

logger = logging.getLogger("kerjapedia.system")

router = APIRouter(prefix="/admin/system", tags=["system-monitoring"])


def _window_cutoff(since_hours: int | None) -> datetime | None:
    if since_hours is None:
        return None
    return datetime.now(UTC) - timedelta(hours=since_hours)


@router.get("/overview")
def system_overview(
    session: DbSession,
    _: AdminUser,
    since_hours: int = Query(default=24, ge=1, le=168),
) -> dict:
    """Overall status, key metrics, recent errors, and active alerts."""
    from app.services.monitoring import (
        evaluate_alerts,
        histogram_percentile,
        merge_histograms,
        probe_all_services,
        process_uptime_seconds,
        record_dependency_probe,
    )

    cutoff = _window_cutoff(since_hours)
    probes = probe_all_services()
    for probe in probes:
        record_dependency_probe(
            service=probe["service"],
            status=probe["status"],
            latency_ms=probe["latency_ms"],
            error=probe["error"],
        )
    active_alerts = evaluate_alerts(session)

    bucket_query = session.query(HttpRequestBucket).filter(
        HttpRequestBucket.route != "__rate_limited__",
        HttpRequestBucket.bucket >= cutoff,
    )
    rows = bucket_query.all()
    total = sum(int(row.count or 0) for row in rows)
    errors = sum(int(row.error_count or 0) for row in rows)
    failed_5xx = sum(
        int(row.count or 0) for row in rows if row.status_class == "5xx"
    )
    count_4xx = sum(
        int(row.count or 0) for row in rows if row.status_class == "4xx"
    )
    successful = sum(
        int(row.count or 0)
        for row in rows
        if row.status_class in ("2xx", "3xx")
    )
    latencies = [int(row.sum_latency_ms or 0) for row in rows]
    merged = merge_histograms([row.latency_histogram for row in rows])
    avg_ms = (sum(latencies) / total) if total else None
    latency = {
        "avg_ms": round(avg_ms, 1) if avg_ms is not None else None,
        "p50_ms": histogram_percentile(merged, total, 0.50),
        "p95_ms": histogram_percentile(merged, total, 0.95),
        "p99_ms": histogram_percentile(merged, total, 0.99),
    }
    window_minutes = max(1, since_hours * 60)
    dep_latency = _dependency_latency(session)
    down = [p["service"] for p in probes if p["status"] == "down"]
    degraded = [p["service"] for p in probes if p["status"] in ("degraded", "unknown")]
    critical_alerts = [a for a in active_alerts if a["severity"] == "critical"]
    overall = "healthy"
    if down or critical_alerts:
        overall = "critical"
    elif degraded or active_alerts:
        overall = "degraded"
    recent_errors = [
        _log_payload(row)
        for row in session.query(SystemLog)
        .filter(SystemLog.level == "error", SystemLog.created_at >= cutoff)
        .order_by(SystemLog.created_at.desc())
        .limit(10)
        .all()
    ]
    return {
        "status": overall,
        "uptime_seconds": round(process_uptime_seconds(), 1),
        "window_hours": since_hours,
        "requests": {
            "total": total,
            "rate_per_minute": round(total / window_minutes, 3),
            "successful": successful,
            "failed_5xx": failed_5xx,
            "count_4xx": count_4xx,
            "error_rate": (errors / total) if total else None,
        },
        "latency_ms": latency,
        "dependencies": {
            probe["service"]: {
                "status": probe["status"],
                "latency_ms": probe["latency_ms"],
                "error": probe["error"],
            }
            for probe in probes
        },
        "dependency_latency_ms": dep_latency,
        "recent_errors": recent_errors,
        "active_alerts": active_alerts,
    }


def _dependency_latency(session) -> dict:
    """24h average + latest latency per probed service from stored probes."""
    from sqlalchemy import text as sa_text

    day_ago = datetime.now(UTC) - timedelta(hours=24)
    rows = (
        session.query(
            DependencyProbe.service,
            func.avg(DependencyProbe.latency_ms),
        )
        .filter(DependencyProbe.checked_at >= day_ago)
        .group_by(DependencyProbe.service)
        .all()
    )
    latest_rows = session.execute(
        sa_text(
            "SELECT DISTINCT ON (service) service, latency_ms"
            " FROM dependency_probes"
            " ORDER BY service, checked_at DESC"
        )
    ).all()
    latest = {str(service): latency for service, latency in latest_rows}
    return {
        str(service): {
            "avg_24h_ms": round(float(avg), 1) if avg is not None else None,
            "last_ms": latest.get(str(service)),
        }
        for service, avg in rows
    }


@router.get("/services")
def system_services(session: DbSession, _: AdminUser) -> dict:
    """Live probe per dependency + 24h averages, error rates, incidents."""
    from app.services.monitoring import probe_all_services, record_dependency_probe

    probes = probe_all_services()
    for probe in probes:
        record_dependency_probe(
            service=probe["service"],
            status=probe["status"],
            latency_ms=probe["latency_ms"],
            error=probe["error"],
        )
    day_ago = datetime.now(UTC) - timedelta(hours=24)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    services = []
    for probe in probes:
        name = probe["service"]
        total = int(
            session.query(func.count(DependencyProbe.probe_id))
            .filter(
                DependencyProbe.service == name,
                DependencyProbe.checked_at >= day_ago,
            )
            .scalar()
            or 0
        )
        bad = int(
            session.query(func.count(DependencyProbe.probe_id))
            .filter(
                DependencyProbe.service == name,
                DependencyProbe.checked_at >= day_ago,
                DependencyProbe.status.in_(("down", "degraded")),
            )
            .scalar()
            or 0
        )
        avg_row = (
            session.query(func.avg(DependencyProbe.latency_ms))
            .filter(
                DependencyProbe.service == name,
                DependencyProbe.checked_at >= day_ago,
                DependencyProbe.latency_ms.is_not(None),
            )
            .scalar()
        )
        incidents = [
            {
                "status": row.status,
                "latency_ms": row.latency_ms,
                "error": row.error,
                "checked_at": row.checked_at,
            }
            for row in session.query(DependencyProbe)
            .filter(
                DependencyProbe.service == name,
                DependencyProbe.checked_at >= week_ago,
                DependencyProbe.status.in_(("down", "degraded")),
            )
            .order_by(DependencyProbe.checked_at.desc())
            .limit(10)
            .all()
        ]
        services.append(
            {
                "service": name,
                "status": probe["status"],
                "latency_ms": probe["latency_ms"],
                "error": probe["error"],
                "last_checked": datetime.now(UTC),
                "avg_24h_ms": round(float(avg_row), 1) if avg_row is not None else None,
                "error_rate_24h": (bad / total) if total else None,
                "recent_incidents": incidents,
            }
        )
    return {"services": services}


def _log_payload(row: SystemLog) -> dict:
    return {
        "log_id": row.log_id,
        "timestamp": row.created_at,
        "level": row.level,
        "service": row.service,
        "message": row.message,
        "request_id": row.request_id,
        "trace_id": row.trace_id,
        "route": row.route,
        "status_code": row.status_code,
        "duration_ms": row.duration_ms,
        "error_type": row.error_type,
    }


@router.get("/logs")
def system_logs(
    session: DbSession,
    _: AdminUser,
    response: Response,
    search: str | None = Query(default=None, max_length=200),
    level: str | None = Query(default=None, max_length=10),
    service: str | None = Query(default=None, max_length=80),
    status: str | None = Query(default=None, max_length=20),
    since_hours: int = Query(default=24, ge=1, le=168),
    limit: int | None = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    query = session.query(SystemLog).filter(
        SystemLog.created_at >= datetime.now(UTC) - timedelta(hours=since_hours)
    )
    if level:
        query = query.filter(SystemLog.level == level)
    if service:
        query = query.filter(SystemLog.service == service)
    if status == "ok":
        query = query.filter(
            (SystemLog.status_code.is_(None)) | (SystemLog.status_code < 400)
        )
    elif status == "error":
        query = query.filter(
            (SystemLog.level == "error")
            | (SystemLog.status_code >= 500)
            | (SystemLog.error_type.in_(("timeout", "provider", "server")))
        )
    if search:
        like = f"%{search[:200]}%"
        query = query.filter(SystemLog.message.ilike(like))
    total = query.count()
    response.headers["X-Total-Count"] = str(total)
    rows = (
        apply_db_pagination(query.order_by(SystemLog.created_at.desc()), limit, offset)
        .all()
    )
    return [_log_payload(row) for row in rows]


@router.get("/logs/{log_id}")
def system_log_detail(log_id: str, session: DbSession, _: AdminUser) -> dict:
    row = session.get(SystemLog, log_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Log entry was not found."
        )
    return _log_payload(row)


def _trace_payload(row: RequestTrace) -> dict:
    return {
        "trace_id": row.trace_id,
        "timestamp": row.started_at,
        "route": row.route,
        "duration_ms": row.duration_ms,
        "status": row.status,
        "span_count": row.span_count,
        "spans": row.spans,
    }


@router.get("/traces")
def system_traces(
    session: DbSession,
    _: AdminUser,
    response: Response,
    route: str | None = Query(default=None, max_length=160),
    status: str | None = Query(default=None, max_length=20),
    since_hours: int = Query(default=24, ge=1, le=168),
    limit: int | None = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    query = session.query(RequestTrace).filter(
        RequestTrace.started_at >= datetime.now(UTC) - timedelta(hours=since_hours)
    )
    if route:
        query = query.filter(RequestTrace.route == route)
    if status:
        query = query.filter(RequestTrace.status == status)
    total = query.count()
    response.headers["X-Total-Count"] = str(total)
    rows = (
        apply_db_pagination(
            query.order_by(RequestTrace.started_at.desc()), limit, offset
        ).all()
    )
    return [
        {key: value for key, value in _trace_payload(row).items() if key != "spans"}
        for row in rows
    ]


@router.get("/traces/{trace_id}")
def system_trace_detail(trace_id: str, session: DbSession, _: AdminUser) -> dict:
    row = session.get(RequestTrace, trace_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trace was not found."
        )
    return _trace_payload(row)


@router.get("/alerts")
def system_alerts(session: DbSession, _: AdminUser) -> dict:
    """Alert rules, currently firing alerts, and recent history."""
    from app.services.monitoring import ALERT_RULES, evaluate_alerts

    active = evaluate_alerts(session)
    recent = [
        {
            "alert_id": row.alert_id,
            "rule": row.rule,
            "severity": row.severity,
            "status": row.status,
            "message": row.message,
            "created_at": row.created_at,
            "resolved_at": row.resolved_at,
        }
        for row in session.query(AlertEvent)
        .order_by(AlertEvent.created_at.desc())
        .limit(20)
        .all()
    ]
    return {"rules": list(ALERT_RULES), "active": active, "recent": recent}
