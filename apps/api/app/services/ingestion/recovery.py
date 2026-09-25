"""Stuck ingestion recovery — no Celery dependency.

Lifespan and tests import from here so recovery works in minimal installs
without the Celery package. The Celery beat task in
:mod:`app.services.ingestion.tasks` is a thin wrapper around
:func:`recover_stuck_ingestion_jobs`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.db.session import create_session

logger = logging.getLogger(__name__)

# A queued/running ingestion that outlives this age had its worker die
# (deploy, OOM, SIGKILL). Recovery marks it failed so admins see it and can
# retry; it never silently resumes or claims success.
STUCK_INGESTION_MAX_AGE = timedelta(hours=2)
_STUCK_JOB_STATUSES = ("queued", "running")


def recover_stuck_ingestion_jobs(
    max_age: timedelta = STUCK_INGESTION_MAX_AGE,
) -> dict[str, int]:
    """Mark ingestion jobs/builds stuck past `max_age` as failed.

    Never touches terminal states (completed/review_required/failed) and never
    downgrades a version that still has a good build. Returns recovered
    counts so startup logs and beat runs stay observable.
    """
    from app.models.ingestion import DocumentVersion, IngestionBuild, IngestionJob

    cutoff = datetime.now(UTC) - max_age
    counts = {"jobs": 0, "builds": 0, "versions": 0}
    with create_session() as session:
        stuck_jobs = (
            session.query(IngestionJob)
            .filter(
                IngestionJob.status.in_(_STUCK_JOB_STATUSES),
                IngestionJob.created_at < cutoff,
            )
            .all()
        )
        for job in stuck_jobs:
            job.status = "failed"
            warnings = list(job.warnings or [])
            if "stuck_recovered:worker_lost" not in warnings:
                warnings.append("stuck_recovered:worker_lost")
            job.warnings = warnings
            counts["jobs"] += 1
        stuck_builds = (
            session.query(IngestionBuild)
            .filter(
                IngestionBuild.status.in_(_STUCK_JOB_STATUSES),
                IngestionBuild.created_at < cutoff,
            )
            .all()
        )
        recovered_version_ids: set[str] = set()
        for build in stuck_builds:
            build.status = "failed"
            quality = dict(build.quality_report or {})
            quality["status"] = "failed"
            quality["failure"] = {
                "stage": "worker",
                "error": "stuck_recovered",
                "detail": "Worker lost before completion; safe to retry.",
            }
            build.quality_report = quality
            counts["builds"] += 1
            recovered_version_ids.add(build.version_id)
        for version_id in recovered_version_ids:
            version = session.get(DocumentVersion, version_id)
            if version is None or version.ingestion_status not in _STUCK_JOB_STATUSES:
                continue
            healthy = (
                session.query(IngestionBuild.build_id)
                .filter(
                    IngestionBuild.version_id == version_id,
                    IngestionBuild.status.in_(("completed", "review_required")),
                )
                .first()
            )
            if healthy is None:
                version.ingestion_status = "failed"
                counts["versions"] += 1
        session.commit()
    if sum(counts.values()):
        logger.warning("stuck ingestion recovery: %s", counts)
    return counts
