from __future__ import annotations

import logging
from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.dependencies import AdminUser, DbSession
from app.api.schemas import IngestionJobRequest
from app.api.utils import (
    dataset_metadata_path,
    load_dataset_documents,
    project_root,
    storage_root,
)
from app.core.config import settings
from app.db.session import create_session
from app.models.ingestion import Document, DocumentVersion, IngestionJob
from app.services.ingestion.metadata import find_document
from app.services.ingestion.pipeline import ingest_document
from app.services.ingestion.uploads import load_uploads_manifest, merge_documents
from app.services.providers import embedding_provider_from_settings, pinecone_store_from_settings

logger = logging.getLogger("kerjapedia.ingestion")

router = APIRouter(prefix="/ingestion/jobs", tags=["ingestion"])


def _run_ingestion_background(
    job_id: str, document_id: str, version_id: str, persist_db: bool
) -> None:
    """Run the heavy ingestion pipeline in a background thread."""
    try:
        extra_manifest_path = storage_root() / "uploads" / "manifest.json"
        result = ingest_document(
            project_root=project_root(),
            metadata_path=dataset_metadata_path(),
            document_id=document_id,
            output_dir=storage_root(),
            embedding_provider=embedding_provider_from_settings(settings),
            database_session_factory=create_session if persist_db else None,
            vector_store=(
                pinecone_store_from_settings(settings)
                if settings.vector_store == "pinecone"
                else None
            ),
            extra_manifest_path=extra_manifest_path,
        )
        with create_session() as session:
            job = session.get(IngestionJob, job_id)
            if job:
                job.status = result.status
                job.warnings = result.warnings or []
                job.artifact_paths = (
                    asdict(result) if hasattr(result, "__dataclass_fields__") else {}
                )
                session.commit()
        # Invalidate admin caches
        try:
            from app.api.routes_admin import _docs_cache, _stats_cache
            _stats_cache.clear()
            _docs_cache.clear()
        except Exception:
            pass
        logger.info("Ingestion job %s completed: %s", job_id, result.status)
    except Exception as exc:
        logger.exception("Ingestion job %s failed", job_id)
        try:
            with create_session() as session:
                job = session.get(IngestionJob, job_id)
                if job:
                    job.status = "failed"
                    job.warnings = [str(exc)]
                    session.commit()
        except Exception:
            logger.exception("Failed to update job %s status", job_id)


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
    job_version_id = f"{document.document_id}_v1"
    session.merge(
        DocumentVersion(
            version_id=job_version_id,
            document_id=document.document_id,
            version=1,
            sha256=document.sha256,
            size_bytes=document.size_bytes,
            local_file=document.local_file,
            source_url=document.source_url,
            legal_status=document.legal_status,
            verification_status=document.verification_status,
            artifact_paths={},
        )
    )
    job_id = f"ing_{uuid4().hex}"
    job = IngestionJob(
        job_id=job_id,
        document_id=payload.document_id,
        version_id=job_version_id,
        status="running",
        warnings=[],
        artifact_paths={},
    )
    session.add(job)
    session.commit()

    background_tasks.add_task(
        _run_ingestion_background,
        job_id=job_id,
        document_id=payload.document_id,
        version_id=job_version_id,
        persist_db=payload.persist_db,
    )

    return {
        "job_id": job.job_id,
        "document_id": job.document_id,
        "status": "running",
        "created_at": job.created_at,
        "warnings": [],
    }


@router.get("")
def list_ingestion_jobs(_: AdminUser, session: DbSession) -> list[dict]:
    rows = session.query(IngestionJob).order_by(IngestionJob.created_at.desc()).all()
    return [
        {
            "job_id": r.job_id,
            "document_id": r.document_id,
            "status": r.status,
            "created_at": r.created_at,
            "warnings": r.warnings,
        }
        for r in rows
    ]


@router.get("/{job_id}")
def get_ingestion_job(job_id: str, session: DbSession, _: AdminUser) -> dict:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job was not found.",
        )
    return {
        "job_id": job.job_id,
        "document_id": job.document_id,
        "status": job.status,
        "created_at": job.created_at,
        "warnings": job.warnings,
        "artifact_paths": job.artifact_paths,
    }
