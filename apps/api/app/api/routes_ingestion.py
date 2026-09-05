from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import text

from app.api.dependencies import AdminUser, DbSession
from app.api.schemas import IngestionJobRequest
from app.api.utils import (
    dataset_metadata_path,
    load_dataset_documents,
    project_root,
    storage_root,
)
from app.core.config import settings
from app.db.session import create_session, engine
from app.models.ingestion import Document, DocumentVersion, IngestionBuild, IngestionJob
from app.services.ingestion.builds import (
    IngestionBuildConfig,
    build_config_from_settings,
    make_build_identity,
    validate_candidate_runtime,
)
from app.services.ingestion.governance import is_canonical_official_source_url
from app.services.ingestion.metadata import find_document
from app.services.ingestion.pipeline import (
    document_version_from_checksum,
    ingest_document,
)
from app.services.ingestion.uploads import load_uploads_manifest, merge_documents
from app.services.providers import embedding_provider_from_settings

logger = logging.getLogger("kerjapedia.ingestion")

router = APIRouter(prefix="/ingestion/jobs", tags=["ingestion"])


def _run_ingestion_background(
    job_id: str,
    document_id: str,
    version_id: str,
    build_id: str,
    persist_db: bool,
) -> None:
    """Run one idempotent ingestion while holding a session-level advisory lock."""
    lock_key = int.from_bytes(
        hashlib.sha256(build_id.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=True,
    )
    lock_connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    acquired = False
    try:
        acquired = bool(
            lock_connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            ).scalar()
        )
        if not acquired:
            logger.info(
                "Ingestion build %s is already running on another worker", build_id
            )
            return
        with create_session() as session:
            job = (
                session.query(IngestionJob)
                .filter(IngestionJob.job_id == job_id)
                .with_for_update()
                .one_or_none()
            )
            build = session.get(IngestionBuild, build_id)
            if (
                job is None
                or build is None
                or job.status in {"completed", "review_required"}
            ):
                return
            job.status = "running"
            build.status = "running"
            build_config = IngestionBuildConfig(**build.pipeline_config)
            session.commit()

        extra_manifest_path = storage_root() / "uploads" / "manifest.json"
        provider = embedding_provider_from_settings(
            settings,
            require_native_sparse=build_config.require_native_sparse,
        )
        result = ingest_document(
            project_root=project_root(),
            metadata_path=dataset_metadata_path(),
            document_id=document_id,
            output_dir=storage_root(),
            embedding_provider=provider,
            database_session_factory=create_session if persist_db else None,
            extra_manifest_path=extra_manifest_path,
            job_id=job_id,
            build_config=build_config,
            resume=True,
        )
        if result.build_id != build_id:
            raise RuntimeError(
                "Worker runtime produced a different ingestion build fingerprint."
            )
        with create_session() as session:
            job = session.get(IngestionJob, job_id)
            build = session.get(IngestionBuild, build_id)
            if job:
                job.status = result.status
                job.version_id = version_id
                job.build_id = build_id
                job.warnings = result.warnings or []
                job.artifact_paths = result.artifacts
            if build:
                build.status = result.status
                build.quality_report = result.quality_report
                build.artifact_manifest = result.artifact_manifest
            version_row = session.get(DocumentVersion, version_id)
            if version_row is not None and not version_row.is_current:
                version_row.ingestion_status = result.status
            session.commit()
        try:
            from app.api.routes_admin import _docs_cache, _stats_cache
            from app.services.retrieval.store import clear_artifact_snapshot_cache

            _stats_cache.clear()
            _docs_cache.clear()
            clear_artifact_snapshot_cache()
        except Exception:
            logger.debug(
                "Unable to invalidate optional ingestion caches", exc_info=True
            )
        logger.info("Ingestion job %s completed: %s", job_id, result.status)
    except Exception as exc:
        logger.exception("Ingestion job %s failed", job_id)
        try:
            with create_session() as session:
                job = session.get(IngestionJob, job_id)
                if job:
                    job.status = "failed"
                    job.warnings = [f"ingestion_failed:{type(exc).__name__}"]
                build = session.get(IngestionBuild, build_id)
                if build:
                    build.status = "failed"
                version_row = session.get(DocumentVersion, version_id)
                if version_row is not None and not version_row.is_current:
                    version_row.ingestion_status = "failed"
                session.commit()
        except Exception:
            logger.exception("Failed to update job %s status", job_id)
        raise
    finally:
        if acquired:
            try:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": lock_key},
                )
            except Exception:
                logger.exception("Failed to release ingestion lock for job %s", job_id)
        lock_connection.close()


@router.post("")
def create_ingestion_job(
    payload: IngestionJobRequest,
    session: DbSession,
    _: AdminUser,
    background_tasks: BackgroundTasks,
) -> dict:
    documents = merge_documents(
        load_dataset_documents(),
        load_uploads_manifest(storage_root()),
    )
    try:
        document = find_document(documents, payload.document_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {payload.document_id} was not found.",
        ) from exc
    if payload.release_candidate and not payload.persist_db:
        raise HTTPException(
            status_code=422,
            detail="A release-candidate ingestion must persist its immutable build to PostgreSQL.",
        )

    provider = embedding_provider_from_settings(
        settings,
        require_native_sparse=(True if payload.release_candidate else None),
    )
    build_config = build_config_from_settings(
        settings,
        provider,
        release_candidate=payload.release_candidate,
    )
    if payload.release_candidate:
        try:
            validate_candidate_runtime(build_config)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    identity = make_build_identity(document.document_id, document.sha256, build_config)

    session.merge(
        Document(
            document_id=document.document_id,
            title=document.title,
            short_title=document.short_title,
            regulation_type=document.regulation_type,
            number=document.number,
            year=document.year,
            issuer=document.issuer,
            topics=document.topics,
        )
    )
    document_version = document_version_from_checksum(document.sha256)
    job_version_id = f"{document.document_id}-v{document_version}"
    version_row = session.get(DocumentVersion, job_version_id)
    if version_row is None:
        version_row = DocumentVersion(
            version_id=job_version_id,
            document_id=document.document_id,
            version=document_version,
            sha256=document.sha256,
            size_bytes=document.size_bytes,
            local_file=document.local_file,
            source_url=document.source_url,
            legal_status=document.legal_status,
            verification_status=document.verification_status,
            source_verification_status=(
                "verified"
                if (
                    document.verification_status == "verified"
                    and is_canonical_official_source_url(document.source_url)
                )
                else "pending"
            ),
            legal_review_status="pending",
            publication_status="draft",
            ingestion_status="queued",
            is_current=False,
            artifact_paths={},
        )
        session.add(version_row)
    session.flush()
    build = session.get(IngestionBuild, identity.build_id)
    if build is None:
        build = IngestionBuild(
            build_id=identity.build_id,
            version_id=job_version_id,
            document_id=document.document_id,
            source_sha256=document.sha256,
            pipeline_version=build_config.pipeline_version,
            config_hash=identity.config_hash,
            pipeline_config=build_config.payload(),
            parser_version=build_config.parser_version,
            chunker_version=build_config.chunker_version,
            ocr_engine=build_config.ocr_profile,
            embedding_model=build_config.embedding_model,
            embedding_revision=build_config.embedding_revision,
            status="queued",
            review_status="pending",
            quality_report={},
            artifact_manifest={},
            page_dispositions={},
            review_notes="",
        )
        session.add(build)

    job_id = f"ing_{identity.build_id.removeprefix('ingb_')}"
    job = session.get(IngestionJob, job_id)
    if job is None:
        job = IngestionJob(
            job_id=job_id,
            document_id=payload.document_id,
            version_id=job_version_id,
            build_id=identity.build_id,
            status="queued",
            warnings=[],
            artifact_paths={},
        )
        session.add(job)
        stale_jobs = (
            session.query(IngestionJob)
            .filter(
                IngestionJob.document_id == payload.document_id,
                IngestionJob.version_id == job_version_id,
                IngestionJob.job_id != job_id,
                IngestionJob.status.in_(["completed", "review_required", "failed"]),
            )
            .all()
        )
        for stale in stale_jobs:
            session.delete(stale)
    elif job.status in {"queued", "running"}:
        return _job_payload(job, build)
    elif job.status == "completed" and not payload.force:
        raise HTTPException(
            status_code=409,
            detail=(
                "Document sudah selesai diingest dan tidak perlu diulang. "
                "Ganti file/sumber terlebih dahulu, atau gunakan force untuk mengulang."
            ),
        )
    else:
        job.build_id = identity.build_id
        job.status = "queued"
        job.warnings = []
        job.artifact_paths = {}
    build.status = "queued"
    session.commit()

    try:
        if settings.celery_enabled:
            from app.services.ingestion.tasks import enqueue_ingestion

            enqueue_ingestion(
                job_id,
                payload.document_id,
                job_version_id,
                identity.build_id,
                payload.persist_db,
            )
        else:
            background_tasks.add_task(
                _run_ingestion_background,
                job_id=job_id,
                document_id=payload.document_id,
                version_id=job_version_id,
                build_id=identity.build_id,
                persist_db=payload.persist_db,
            )
    except Exception as exc:
        job.status = "failed"
        job.warnings = ["ingestion_queue_unavailable"]
        build.status = "failed"
        session.commit()
        raise HTTPException(
            status_code=503,
            detail="The ingestion queue is temporarily unavailable.",
        ) from exc

    return _job_payload(job, build)


@router.get("")
def list_ingestion_jobs(_: AdminUser, session: DbSession) -> list[dict]:
    rows = session.query(IngestionJob).order_by(IngestionJob.created_at.desc()).all()
    avg_duration = _average_build_duration(session)
    return [
        _job_payload(
            row,
            session.get(IngestionBuild, row.build_id) if row.build_id else None,
            avg_duration=avg_duration,
        )
        for row in rows
    ]


@router.get("/{job_id}")
def get_ingestion_job(job_id: str, session: DbSession, _: AdminUser) -> dict:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job was not found.",
        )
    build = session.get(IngestionBuild, job.build_id) if job.build_id else None
    payload = _job_payload(job, build, avg_duration=_average_build_duration(session))
    payload["artifact_paths"] = job.artifact_paths
    return payload


def _average_build_duration(session) -> float | None:
    """Average duration of completed builds in seconds, used to estimate ETA."""
    rows = (
        session.query(IngestionBuild.completed_at, IngestionBuild.created_at)
        .filter(
            IngestionBuild.completed_at.is_not(None),
            IngestionBuild.status.in_(["completed", "review_required"]),
        )
        .all()
    )
    durations = [
        (completed - created).total_seconds()
        for (completed, created) in rows
        if completed is not None and (completed - created).total_seconds() > 0
    ]
    if not durations:
        return None
    return sum(durations) / len(durations)


def _job_payload(
    job: IngestionJob,
    build: IngestionBuild | None,
    avg_duration: float | None = None,
) -> dict:
    status = "needs_review" if job.status == "review_required" else job.status
    created = job.created_at
    now = datetime.now(UTC)
    elapsed_seconds = (
        (now - created).total_seconds()
        if created is not None and status in {"running", "queued"}
        else None
    )
    stored = job.artifact_paths or {}
    quality_report = (build.quality_report or {}) if build else {}
    chunk_count = quality_report.get("chunks", {}).get("count")
    if chunk_count is None:
        chunk_count = stored.get("chunk_count")
    return {
        "job_id": job.job_id,
        "build_id": job.build_id,
        "document_id": job.document_id,
        "status": status,
        "created_at": job.created_at,
        "updated_at": job.created_at,
        "elapsed_seconds": elapsed_seconds,
        "avg_duration_seconds": avg_duration,
        "warnings": job.warnings,
        "result": {
            **({"chunk_count": int(chunk_count)} if chunk_count is not None else {}),
            "warnings": job.warnings or [],
        },
        "error": next(
            (
                item
                for item in (job.warnings or [])
                if item.startswith("ingestion_failed:")
            ),
            None,
        ),
        "quality_report": build.quality_report if build else {},
        "review_status": build.review_status if build else "pending",
    }
