from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AdminUser
from app.api.schemas import IngestionJobRequest
from app.api.state import now_utc, state
from app.api.utils import dataset_metadata_path, project_root, storage_root
from app.core.config import settings
from app.db.session import create_session
from app.services.ingestion.pipeline import ingest_document
from app.services.providers import embedding_provider_from_settings, pinecone_store_from_settings

router = APIRouter(prefix="/ingestion/jobs", tags=["ingestion"])


@router.post("")
def create_ingestion_job(
    payload: IngestionJobRequest,
    _: AdminUser,
) -> dict:
    job_id = f"ing_{uuid4().hex}"
    state.ingestion_jobs[job_id] = {
        "job_id": job_id,
        "document_id": payload.document_id,
        "status": "running",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "result": None,
    }
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
        state.ingestion_jobs[job_id]["status"] = result.status
        state.ingestion_jobs[job_id]["result"] = asdict(result)
    except Exception as exc:
        state.ingestion_jobs[job_id]["status"] = "failed"
        state.ingestion_jobs[job_id]["error"] = str(exc)
    finally:
        state.ingestion_jobs[job_id]["updated_at"] = now_utc()

    return state.ingestion_jobs[job_id]


@router.get("")
def list_ingestion_jobs(_: AdminUser) -> list[dict]:
    return sorted(
        state.ingestion_jobs.values(),
        key=lambda item: item["updated_at"],
        reverse=True,
    )


@router.get("/{job_id}")
def get_ingestion_job(
    job_id: str,
    _: AdminUser,
) -> dict:
    job = state.ingestion_jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job was not found.",
        )
    return job
