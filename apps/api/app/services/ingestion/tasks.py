from __future__ import annotations

from datetime import UTC, datetime, timedelta

from celery import Celery
from sqlalchemy import text

from app.core.config import settings
from app.db.session import create_session

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
        }
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
