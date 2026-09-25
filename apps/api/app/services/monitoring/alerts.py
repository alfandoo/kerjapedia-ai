"""Code-driven alert rules over monitoring aggregates (no fake integrations).

Rules evaluate on overview reads and persist firing/resolved
:class:`AlertEvent` rows with a 15-minute re-fire cooldown. There is no
email/Slack/Discord provider by design (§12): the event model plus the
Alerts UI is the notification surface until a provider is approved.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

logger = logging.getLogger("kerjapedia.system")

ALERT_COOLDOWN = timedelta(minutes=15)

ALERT_RULES: tuple[dict, ...] = (
    {
        "rule": "error_rate_high",
        "severity": "critical",
        "description": "Error rate > 5% over the last 5 minutes",
    },
    {
        "rule": "p95_latency_high",
        "severity": "warning",
        "description": "p95 latency > 3000ms over the last 10 minutes",
    },
    {
        "rule": "service_down",
        "severity": "critical",
        "description": "A dependency probe reports down",
    },
    {
        "rule": "repeated_timeouts",
        "severity": "warning",
        "description": "3+ timeouts in the last 15 minutes",
    },
    {
        "rule": "rate_limit_spike",
        "severity": "warning",
        "description": "20+ rate-limited responses in the last 15 minutes",
    },
)

ERROR_RATE_THRESHOLD = 0.05
P95_LATENCY_MS_THRESHOLD = 3000.0
TIMEOUT_COUNT_THRESHOLD = 3
RATE_LIMIT_COUNT_THRESHOLD = 20


def check_rules(snapshot: dict) -> list[dict]:
    """Pure rule evaluation over a pre-aggregated snapshot (unit-testable)."""
    active: list[dict] = []
    error_rate = snapshot.get("error_rate_5m")
    if error_rate is not None and error_rate > ERROR_RATE_THRESHOLD:
        active.append(
            {
                "rule": "error_rate_high",
                "severity": "critical",
                "message": f"Error rate {error_rate:.1%} over the last 5 minutes.",
            }
        )
    p95 = snapshot.get("p95_10m_ms")
    if p95 is not None and p95 > P95_LATENCY_MS_THRESHOLD:
        active.append(
            {
                "rule": "p95_latency_high",
                "severity": "warning",
                "message": f"p95 latency {p95:.0f}ms over the last 10 minutes.",
            }
        )
    for service in snapshot.get("services_down") or []:
        active.append(
            {
                "rule": "service_down",
                "severity": "critical",
                "message": f"Dependency {service} reports down.",
            }
        )
    timeouts = int(snapshot.get("timeouts_15m") or 0)
    if timeouts >= TIMEOUT_COUNT_THRESHOLD:
        active.append(
            {
                "rule": "repeated_timeouts",
                "severity": "warning",
                "message": f"{timeouts} timeouts in the last 15 minutes.",
            }
        )
    limited = int(snapshot.get("rate_limited_15m") or 0)
    if limited >= RATE_LIMIT_COUNT_THRESHOLD:
        active.append(
            {
                "rule": "rate_limit_spike",
                "severity": "warning",
                "message": f"{limited} rate-limited responses in the last 15 minutes.",
            }
        )
    return active


def evaluate_alerts(session) -> list[dict]:
    """Gather a snapshot, persist transitions, return active alerts."""
    from sqlalchemy import func

    from app.models.business import HttpRequestBucket

    now = datetime.now(UTC)
    recent_5m = now - timedelta(minutes=5)
    recent_10m = now - timedelta(minutes=10)
    recent_15m = now - timedelta(minutes=15)

    def _sums(since, status_filter=None):
        query = session.query(
            func.coalesce(func.sum(HttpRequestBucket.count), 0),
            func.coalesce(func.sum(HttpRequestBucket.error_count), 0),
        ).filter(HttpRequestBucket.bucket >= since)
        if status_filter:
            query = query.filter(HttpRequestBucket.status_class.in_(status_filter))
        total, errors = query.one()
        return int(total or 0), int(errors or 0)

    total_5m, errors_5m = _sums(recent_5m)
    p95_10m = _bucket_p95(session, recent_10m)
    timeouts_15m = _outcome_count(session, recent_15m, ("timeout_retrieval", "timeout_generation"))
    limited_15m = _status_count(session, recent_15m)
    services_down = _services_down(session, now - timedelta(minutes=10))

    snapshot = {
        "error_rate_5m": (errors_5m / total_5m) if total_5m else None,
        "p95_10m_ms": p95_10m,
        "services_down": services_down,
        "timeouts_15m": timeouts_15m,
        "rate_limited_15m": limited_15m,
    }
    active = check_rules(snapshot)
    try:
        _persist_transitions(session, active, now)
        session.commit()
    except Exception:
        session.rollback()
        logger.debug("alert persist skipped", exc_info=True)
    return active


def _bucket_p95(session, since) -> float | None:
    from app.models.business import HttpRequestBucket
    from app.services.monitoring.collector import histogram_percentile, merge_histograms

    rows = (
        session.query(HttpRequestBucket.latency_histogram)
        .filter(HttpRequestBucket.bucket >= since)
        .all()
    )
    histograms = [row[0] for row in rows]
    total = sum(
        sum(int(value or 0) for value in (hist or {}).values()) for hist in histograms
    )
    if not total:
        return None
    return histogram_percentile(merge_histograms(histograms), total, 0.95)


def _outcome_count(session, since, outcomes: tuple[str, ...]) -> int:
    from sqlalchemy import func

    from app.models.business import RagRequestObservation

    return int(
        session.query(func.count(RagRequestObservation.id))
        .filter(
            RagRequestObservation.created_at >= since,
            RagRequestObservation.outcome.in_(outcomes),
        )
        .scalar()
        or 0
    )


def _status_count(session, since) -> int:
    from sqlalchemy import func

    from app.models.business import HttpRequestBucket

    return int(
        session.query(func.coalesce(func.sum(HttpRequestBucket.count), 0))
        .filter(
            HttpRequestBucket.bucket >= since,
            HttpRequestBucket.route == "__rate_limited__",
        )
        .scalar()
        or 0
    )


def _services_down(session, since) -> list[str]:
    from app.models.business import DependencyProbe

    rows = (
        session.query(DependencyProbe.service)
        .filter(
            DependencyProbe.checked_at >= since,
            DependencyProbe.status == "down",
        )
        .distinct()
        .all()
    )
    return sorted({str(row[0]) for row in rows})


def _persist_transitions(session, active: list[dict], now: datetime) -> None:
    from app.models.business import AlertEvent

    active_rules = {item["rule"] for item in active}
    firing = {
        str(row.rule): row
        for row in session.query(AlertEvent)
        .filter(AlertEvent.status == "firing")
        .all()
    }
    for item in active:
        existing = firing.get(item["rule"])
        if existing is not None:
            continue
        recent = (
            session.query(AlertEvent)
            .filter(
                AlertEvent.rule == item["rule"],
                AlertEvent.status == "resolved",
                AlertEvent.resolved_at >= now - ALERT_COOLDOWN,
            )
            .first()
        )
        if recent is not None:
            continue
        session.add(
            AlertEvent(
                alert_id=f"alr_{uuid4().hex}",
                rule=item["rule"],
                severity=item["severity"],
                status="firing",
                message=item["message"],
                created_at=now,
            )
        )
    for rule, row in firing.items():
        if rule not in active_rules:
            row.status = "resolved"
            row.resolved_at = now
