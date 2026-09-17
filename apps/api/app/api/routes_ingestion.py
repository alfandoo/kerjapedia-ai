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
    document_metadata_hash,
    make_build_identity,
    validate_candidate_runtime,
)
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
            if version_row is not None:
                _advance_version_ingestion_status(version_row, result.status)
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
                    failed_ids = list(getattr(exc, "failed_item_ids", ()))
                    job.warnings = [
                        f"ingestion_failed:{type(exc).__name__}",
                        *(
                            [
                                f"failed_items:{len(failed_ids)}:"
                                + ",".join(failed_ids[:20])
                            ]
                            if failed_ids
                            else []
                        ),
                    ]
                build = session.get(IngestionBuild, build_id)
                if build:
                    build.status = "failed"
                    current_quality = dict(build.quality_report or {})
                    current_statistics = dict(
                        current_quality.get("ingestion_statistics") or {}
                    )
                    if failed_ids:
                        current_statistics["failed_embeddings"] = len(failed_ids)
                    if hasattr(exc, "duration_seconds"):
                        current_statistics["embedding_duration_seconds"] = float(
                            exc.duration_seconds
                        )
                    build.quality_report = {
                        **current_quality,
                        "status": "failed",
                        "ingestion_statistics": current_statistics,
                        "failure": {
                            "stage": "embedding" if failed_ids else "ingestion",
                            "error": type(exc).__name__,
                            "failed_item_count": len(failed_ids),
                            "failed_item_ids": failed_ids[:100],
                        },
                    }
                version_row = session.get(DocumentVersion, version_id)
                if version_row is not None:
                    _advance_version_ingestion_status(version_row, "failed")
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
    identity = make_build_identity(
        document.document_id,
        document.sha256,
        build_config,
        document_metadata_hash(document),
    )

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
    calculated_version_id = f"{document.document_id}-v{document_version}"
    version_row = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.sha256 == document.sha256)
        .one_or_none()
    )
    if version_row is not None and version_row.document_id != document.document_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Source PDF is already registered to another document; ingestion "
                "was not queued."
            ),
        )
    if version_row is None:
        collision = session.get(DocumentVersion, calculated_version_id)
        if collision is not None and collision.sha256 != document.sha256:
            raise HTTPException(
                status_code=409,
                detail="Document version identity collision; ingestion was not queued.",
            )
        job_version_id = calculated_version_id
    else:
        job_version_id = version_row.version_id
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
            source_verification_status=document.source_verification_status,
            legal_review_status=document.legal_review_status,
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
            metadata_hash=identity.metadata_hash,
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
    elif (
        build.version_id != job_version_id
        or build.source_sha256 != document.sha256
        or build.config_hash != identity.config_hash
        or build.metadata_hash != identity.metadata_hash
    ):
        raise HTTPException(
            status_code=409,
            detail="Existing ingestion build has conflicting provenance.",
        )

    job_id = f"ing_{identity.build_id.removeprefix('ingb_')}"
    job = session.get(IngestionJob, job_id)
    if build.status in {"completed", "review_required"}:
        if job is None:
            job = IngestionJob(
                job_id=job_id,
                document_id=payload.document_id,
                version_id=job_version_id,
                build_id=identity.build_id,
                status=build.status,
                warnings=[],
                artifact_paths={},
            )
            session.add(job)
        else:
            job.status = build.status
            job.version_id = job_version_id
            job.build_id = identity.build_id
        session.commit()
        try:
            from app.api.routes_admin import _stats_cache

            _stats_cache.clear()
        except Exception:
            logger.debug("Unable to invalidate admin stats cache", exc_info=True)
        return _job_payload(job, build)
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
    elif job.status in {"queued", "running"}:
        return _job_payload(job, build)
    elif (
        job.status in {"completed", "review_required"}
        and build.status in {"completed", "review_required"}
    ):
        return _job_payload(job, build)
    else:
        job.build_id = identity.build_id
        job.status = "queued"
        job.warnings = []
        job.artifact_paths = {}
    build.status = "queued"
    build.completed_at = None
    build.quality_report = {}
    build.artifact_manifest = {}
    session.commit()
    try:
        from app.api.routes_admin import _stats_cache

        _stats_cache.clear()
    except Exception:
        logger.debug("Unable to invalidate admin stats cache", exc_info=True)

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


def _advance_version_ingestion_status(
    version: DocumentVersion,
    candidate_status: str,
) -> None:
    """Never let a failed or review-only build replace a completed candidate."""
    if version.is_current:
        return
    if candidate_status == "completed" or version.ingestion_status != "completed":
        version.ingestion_status = candidate_status


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


# ---------------------------------------------------------------------------
# Re-embed endpoint: migrate chunks to Upstash Vector
# ---------------------------------------------------------------------------

@router.post("/reembed")
def reembed_to_upstash(
    _: AdminUser,
    session: DbSession,
) -> dict:
    """Read all chunks from PostgreSQL and upsert to Upstash Vector.

    Dense: text-embedding-3-small (1536d) via OpenAI
    Sparse: BM25 lexical scoring
    """
    if not settings.upstash_vector_url or not settings.upstash_vector_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN must be set.",
        )
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is required for text-embedding-3-small embeddings.",
        )

    from app.models.ingestion import DocumentChunk
    from app.services.retrieval.upstash_vector_store import UpstashVectorConfig, UpstashVectorStore

    chunks = session.query(DocumentChunk).all()
    if not chunks:
        return {"status": "no_chunks", "upserted": 0}

    upsert_chunks = []
    for chunk in chunks:
        doc = session.query(Document).filter_by(document_id=chunk.document_id).first()
        topics = []
        legal_status = "active"
        source_url = ""
        if doc:
            doc_meta = doc.payload or {}
            topics = doc_meta.get("topics", [])
            legal_status = doc_meta.get("legal_status", "active")
            source_url = doc_meta.get("source_url", "")

        upsert_chunks.append({
            "chunk_id": chunk.chunk_id,
            "text": chunk.retrieval_text or chunk.text,
            "metadata": {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "version_id": chunk.version_id,
                "chapter": chunk.chapter or "",
                "section": chunk.section or "",
                "article": chunk.article or "",
                "paragraph": chunk.paragraph or "",
                "page_start": chunk.page_start or 0,
                "page_end": chunk.page_end or 0,
                "token_count": chunk.token_count or 0,
                "text": (chunk.text or "")[:10000],
                "retrieval_text": (chunk.retrieval_text or chunk.text or "")[:10000],
                "topics": topics,
                "legal_status": legal_status,
                "source_url": source_url,
                "embedding_model": "text-embedding-3-small",
            },
        })

    config = UpstashVectorConfig(
        url=settings.upstash_vector_url,
        token=settings.upstash_vector_token,
        dimension=settings.upstash_vector_dimension,
        namespace=settings.upstash_vector_namespace,
    )
    store = UpstashVectorStore(
        config=config,
        openai_api_key=settings.openai_api_key,
    )

    upserted = store.upsert_chunks(upsert_chunks, batch_size=100)

    return {
        "status": "completed",
        "total_chunks": len(chunks),
        "upserted": upserted,
        "embedding_model": "text-embedding-3-small",
        "dimension": settings.upstash_vector_dimension,
    }


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
