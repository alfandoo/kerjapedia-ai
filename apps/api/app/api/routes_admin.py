from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func as sa_func

from app.api.dependencies import AdminUser, DbSession
from app.api.schemas import (
    DocumentRelationshipRequest,
    DocumentUpdateRequest,
    PublicationRequest,
    RetrievalPlaygroundRequest,
)
from app.api.state import now_utc
from app.api.utils import (
    dataset_metadata_path,
    find_dataset_document,
    load_dataset_documents,
    storage_root,
)
from app.api.utils import project_root as get_project_root
from app.core.config import settings
from app.models.business import (
    Conversation,
    DocumentAdmin,
    Feedback,
    Message,
    UploadedDocument,
    UserProfile,
)
from app.models.ingestion import IngestionJob
from app.services.providers import pinecone_store_from_settings
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.store import load_artifact_documents
from app.services.storage import upload_bytes

router = APIRouter(prefix="/admin", tags=["admin"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def project_root() -> Path:
    return get_project_root()


def _manifest_relationships() -> list[dict]:
    data = json.loads(dataset_metadata_path().read_text(encoding="utf-8"))
    return     data.get("relationships", [])


def _now_iso() -> str:
    return now_utc().isoformat()


def _get_or_create_admin_record(document_id: str, session) -> DocumentAdmin:
    record = session.get(DocumentAdmin, document_id)
    if record is None:
        relationships = [
            item
            for item in _manifest_relationships()
            if item["from_document_id"] == document_id
        ]
        record = DocumentAdmin(
            document_id=document_id,
            publication_status="draft",
            version=1,
            relationships=relationships,
            versions_history=[
                {"version": 1, "status": "draft", "created_at": _now_iso(), "created_by": "System"}
            ],
        )
        session.add(record)
        session.commit()
    return record


def _latest_jobs(session) -> dict[str, dict]:
    from app.models.ingestion import IngestionJob

    jobs: dict[str, dict] = {}
    rows = (
        session.query(IngestionJob)
        .order_by(IngestionJob.created_at.desc())
        .all()
    )
    for job in rows:
        jobs.setdefault(job.document_id, {
            "job_id": job.job_id,
            "document_id": job.document_id,
            "status": job.status,
            "error": None,
            "updated_at": job.created_at,
        })
    return jobs


@router.get("/stats")
def admin_stats(session: DbSession, _: AdminUser) -> dict:
    documents = load_dataset_documents()
    chunks = load_artifact_documents(storage_root())
    chunk_counts: dict[str, int] = {}
    for chunk in chunks:
        chunk_counts[chunk.document_id] = chunk_counts.get(chunk.document_id, 0) + 1
    jobs = _latest_jobs(session)

    doc_counts = {"total": len(documents), "published": 0, "needs_review": 0, "failed": 0}
    for doc in documents:
        record = session.get(DocumentAdmin, doc.document_id)
        pub = record.publication_status if record else "draft"
        job = jobs.get(doc.document_id)
        ing_status = (
            job["status"]
            if job
            else ("completed" if chunk_counts.get(doc.document_id, 0) else "needs_review")
        )
        if pub == "published":
            doc_counts["published"] += 1
        if ing_status == "needs_review":
            doc_counts["needs_review"] += 1
        if ing_status == "failed":
            doc_counts["failed"] += 1

    user_count = session.query(UserProfile).count()
    conversation_count = session.query(Conversation).count()
    message_count = session.query(sa_func.count(Message.message_id)).scalar() or 0
    feedback_count = session.query(Feedback).count()
    feedback_helpful = session.query(Feedback).filter(
        Feedback.rating == "helpful"
    ).count()
    job_count = session.query(IngestionJob).count()
    recent_jobs = (
        session.query(IngestionJob)
        .order_by(IngestionJob.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "documents": doc_counts,
        "users": user_count,
        "conversations": conversation_count,
        "messages": message_count,
        "feedback": {
            "total": feedback_count,
            "helpful": feedback_helpful,
            "not_helpful": feedback_count - feedback_helpful,
        },
        "ingestion_jobs": {
            "total": job_count,
            "recent": [
                {
                    "job_id": j.job_id,
                    "document_id": j.document_id,
                    "status": j.status,
                    "created_at": j.created_at.isoformat(),
                }
                for j in recent_jobs
            ],
        },
    }


@router.get("/documents")
def list_admin_documents(session: DbSession, _: AdminUser) -> dict:
    documents = load_dataset_documents()
    chunks = load_artifact_documents(storage_root())
    chunk_counts: dict[str, int] = {}
    for chunk in chunks:
        chunk_counts[chunk.document_id] = chunk_counts.get(chunk.document_id, 0) + 1
    jobs = _latest_jobs(session)
    results = []

    for _index, document in enumerate(documents):
        record = _get_or_create_admin_record(document.document_id, session)
        job = jobs.get(document.document_id)
        ingestion_status = (
            job["status"]
            if job
            else ("completed" if chunk_counts.get(document.document_id, 0) else "needs_review")
        )
        payload = asdict(document)
        payload.update(record.overrides)
        payload.update(
            {
                "ingestion_status": ingestion_status,
                "chunk_count": chunk_counts.get(document.document_id, 0),
                "publication_status": record.publication_status,
                "version": record.version,
                "updated_at": record.updated_at,
                "updated_by": record.updated_by,
                "relationships": record.relationships,
                "versions": list(reversed(record.versions_history)),
                "last_error": job.get("error") if job else None,
            }
        )
        results.append(payload)

    summary = {
        "documents": len(results),
        "published": sum(item["publication_status"] == "published" for item in results),
        "needs_review": sum(item["ingestion_status"] == "needs_review" for item in results),
        "failed": sum(item["ingestion_status"] == "failed" for item in results),
    }
    return {"summary": summary, "documents": results}


@router.patch("/documents/{document_id}")
def update_admin_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    session: DbSession,
    _: AdminUser,
) -> dict:
    find_dataset_document(document_id)
    record = _get_or_create_admin_record(document_id, session)
    changes = payload.model_dump(exclude_none=True)
    record.overrides = {**record.overrides, **changes}
    record.updated_at = now_utc()
    session.commit()
    return {"status": "updated", "document_id": document_id, "changes": changes}


@router.put("/documents/{document_id}/relationships")
def replace_relationships(
    document_id: str,
    payload: list[DocumentRelationshipRequest],
    session: DbSession,
    _: AdminUser,
) -> dict:
    find_dataset_document(document_id)
    relationships = []
    for relationship in payload:
        find_dataset_document(relationship.to_document_id)
        relationships.append(
            {
                "from_document_id": document_id,
                **relationship.model_dump(),
            }
        )
    record = _get_or_create_admin_record(document_id, session)
    record.relationships = relationships
    record.updated_at = now_utc()
    session.commit()
    return {"status": "updated", "relationships": relationships}


@router.post("/documents/{document_id}/publication")
def update_publication(
    document_id: str,
    payload: PublicationRequest,
    session: DbSession,
    _: AdminUser,
) -> dict:
    find_dataset_document(document_id)
    record = _get_or_create_admin_record(document_id, session)
    publication_status = "published" if payload.action == "publish" else "draft"
    record.version += 1
    record.publication_status = publication_status
    record.updated_at = now_utc()
    record.versions_history.append(
        {
            "version": record.version,
            "status": publication_status,
            "created_at": _now_iso(),
            "created_by": "Admin",
        }
    )
    session.commit()
    return {
        "status": publication_status,
        "version": record.version,
        "versions": list(reversed(record.versions_history)),
    }


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    session: DbSession,
    _: AdminUser,
    file_name: str = Query(min_length=5, max_length=180),
    topic: str = Query(default="uncategorized", min_length=2, max_length=80),
) -> dict:
    safe_name = Path(file_name).name
    if Path(safe_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    content = await request.body()
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF file exceeds the 50 MB limit.")

    upload_id = f"upload_{uuid4().hex}"
    document_id = re.sub(r"[^A-Z0-9]+", "-", Path(safe_name).stem.upper()).strip("-")
    storage_path = f"uploads/{upload_id}_{safe_name}"

    public_url = upload_bytes(content, storage_path)

    uploaded = UploadedDocument(
        upload_id=upload_id,
        document_id=document_id,
        file_name=safe_name,
        storage_path=storage_path,
        topic=topic,
        size_bytes=len(content),
        status="uploaded",
    )
    session.add(uploaded)
    session.commit()
    return {
        "upload_id": upload_id,
        "document_id": document_id,
        "file_name": safe_name,
        "topic": topic,
        "size_bytes": len(content),
        "status": "uploaded",
        "storage_url": public_url,
        "created_at": uploaded.created_at,
    }


@router.post("/retrieval/search")
def retrieval_playground(
    payload: RetrievalPlaygroundRequest,
    _: AdminUser,
) -> dict:
    started_at = time.perf_counter()
    try:
        if settings.vector_store == "pinecone":
            response = pinecone_store_from_settings(settings).search(
                payload.question,
                top_k=payload.top_k,
            )
        else:
            engine = RetrievalEngine(
                documents=load_artifact_documents(storage_root()),
                top_k=payload.top_k,
            )
            response = engine.search(payload.question, top_k=payload.top_k)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    results = []
    for item in response.results:
        document = item.document
        results.append(
            {
                "chunk_id": document.chunk_id,
                "document_id": document.document_id,
                "short_title": document.metadata.get("short_title", document.document_id),
                "article": document.article,
                "page_start": document.page_start,
                "page_end": document.page_end,
                "quote": document.text,
                "lexical_score": item.lexical_score,
                "semantic_score": item.semantic_score,
                "rerank_score": item.rerank_score,
                "final_score": item.final_score,
                "match_reasons": item.match_reasons,
            }
        )
    return {
        "query": payload.question,
        "latency_ms": int((time.perf_counter() - started_at) * 1000),
        "warnings": response.warnings,
        "should_refuse": response.should_refuse,
        "results": results,
    }
