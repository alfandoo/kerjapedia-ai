from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AdminUser, DbSession
from app.api.schemas import IngestionJobRequest
from app.api.utils import dataset_metadata_path, project_root, storage_root
from app.core.config import settings
from app.db.session import create_session
from app.models.ingestion import IngestionJob
from app.services.ingestion.pipeline import ingest_document
from app.services.providers import embedding_provider_from_settings, pinecone_store_from_settings

router = APIRouter(prefix="/ingestion/jobs", tags=["ingestion"])


@router.post("")
def create_ingestion_job(
    payload: IngestionJobRequest,
    session: DbSession,
    _: AdminUser,
) -> dict:
    job_id = f"ing_{uuid4().hex}"
    job = IngestionJob(
        job_id=job_id,
        document_id=payload.document_id,
        version_id=f"{payload.document_id}_v1",
        status="running",
        warnings=[],
        artifact_paths={},
    )
    session.add(job)
    session.commit()

    try:
        result = ingest_document(
            project_root=project_root(),
            metadata_path=dataset_metadata_path(),
            document_id=payload.document_id,
            output_dir=storage_root(),
            embedding_provider=embedding_provider_from_settings(settings),
            database_session_factory=create_session if payload.persist_db else None,
            vector_store=(
                pinecone_store_from_settings(settings)
                if settings.vector_store == "pinecone"
                else None
            ),
        )
        job.status = result.status
        job.warnings = result.warnings or []
        job.artifact_paths = asdict(result) if hasattr(result, "__dataclass_fields__") else {}
    except Exception as exc:
        job.status = "failed"
        job.warnings = [str(exc)]
    session.commit()
    return {
        "job_id": job.job_id,
        "document_id": job.document_id,
        "status": job.status,
        "created_at": job.created_at,
        "warnings": job.warnings,
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
