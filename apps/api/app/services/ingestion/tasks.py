from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from celery import Celery
from sqlalchemy import text

from app.core.config import settings
from app.db.session import create_session
from app.services.ingestion.recovery import (
    STUCK_INGESTION_MAX_AGE,  # noqa: F401  (re-exported for beat/tests)
    recover_stuck_ingestion_jobs,
)

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kerjapedia_ingestion",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "purge-expired-rag-traces-daily": {
            "task": "kerjapedia.rag.purge_expired_traces",
            "schedule": 86_400.0,
        },
        "monitoring-cleanup-daily": {
            "task": "kerjapedia.system.cleanup",
            "schedule": 86_400.0,
        },
        "recover-stuck-ingestion-hourly": {
            "task": "kerjapedia.ingestion.recover_stuck",
            "schedule": 3_600.0,
        },
        "fail-stuck-evaluations-hourly": {
            "task": "kerjapedia.evaluation.fail_stuck",
            "schedule": 3_600.0,
        },
    },
)


@celery_app.task(
    bind=True,
    name="kerjapedia.ingestion.run",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def run_ingestion_task(
    _task,
    job_id: str,
    document_id: str,
    version_id: str,
    build_id: str,
    persist_db: bool,
) -> None:
    from app.api.routes_ingestion import _run_ingestion_background

    _run_ingestion_background(job_id, document_id, version_id, build_id, persist_db)


def enqueue_ingestion(
    job_id: str,
    document_id: str,
    version_id: str,
    build_id: str,
    persist_db: bool,
) -> None:
    run_ingestion_task.delay(job_id, document_id, version_id, build_id, persist_db)


@celery_app.task(
    bind=True,
    name="kerjapedia.ingestion.reembed",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def run_reembed_task(_task) -> dict:
    from app.api.routes_ingestion import _run_reembed_sync

    return _run_reembed_sync()


def enqueue_reembed() -> None:
    run_reembed_task.delay()


@celery_app.task(name="kerjapedia.ingestion.recover_stuck")
def recover_stuck_ingestion() -> dict[str, int]:
    return recover_stuck_ingestion_jobs()


@celery_app.task(name="kerjapedia.system.cleanup")
def monitoring_cleanup() -> dict[str, int]:
    from app.services.monitoring.collector import cleanup_monitoring

    return cleanup_monitoring()


@celery_app.task(name="kerjapedia.rag.purge_expired_traces")
def purge_expired_rag_traces() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=settings.rag_trace_retention_days)
    with create_session() as session:
        result = session.execute(
            text(
                "UPDATE messages SET metadata = metadata - 'rag_trace' "
                "WHERE created_at < :cutoff AND metadata->'rag_trace' IS NOT NULL"
            ),
            {"cutoff": cutoff},
        )
        session.commit()
        return int(result.rowcount or 0)
