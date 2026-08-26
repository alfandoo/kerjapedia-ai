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
from app.services.audit import list_audit_logs, log_audit
from app.services.ingestion.manifest_updater import (
    MANIFEST_EDITABLE_FIELDS,
    manifest_contains,
    update_manifest_metadata,
)
from app.services.ingestion.uploads import (
    load_uploads_manifest,
    merge_documents,
    register_upload,
)
from app.services.providers import pinecone_store_from_settings
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.relationships import relationship_index_for_manifest
from app.services.retrieval.store import count_chunks_per_document, load_artifact_documents
from app.services.storage import upload_bytes

router = APIRouter(prefix="/admin", tags=["admin"])

_stats_cache: dict[str, tuple[float, dict]] = {}
_docs_cache: dict[str, tuple[float, dict]] = {}
_STATS_CACHE_TTL = 30  # seconds
_DOCS_CACHE_TTL = 30
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
    cache_key = "stats"
    cached = _stats_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _STATS_CACHE_TTL:
        return cached[1]

    documents = load_dataset_documents()
    chunk_counts = count_chunks_per_document(storage_root())
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

    result = {
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
    _stats_cache[cache_key] = (time.time(), result)
    return result


@router.get("/documents")
def list_admin_documents(session: DbSession, _: AdminUser) -> dict:
    cache_key = "documents"
    cached = _docs_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _DOCS_CACHE_TTL:
        return cached[1]

    documents = merge_documents(
        load_dataset_documents(),
        load_uploads_manifest(storage_root()),
    )
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
    result = {"summary": summary, "documents": results}
    _docs_cache[cache_key] = (time.time(), result)
    return result


@router.patch("/documents/{document_id}")
def update_admin_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    session: DbSession,
    user: AdminUser,
) -> dict:
    _stats_cache.clear()
    _docs_cache.clear()
    dataset_path = dataset_metadata_path()
    changes = payload.model_dump(exclude_none=True)

    manifest_path = dataset_path
    if not manifest_contains(manifest_path, document_id):
        upload_path = storage_root() / "uploads" / "manifest.json"
        if manifest_contains(upload_path, document_id):
            manifest_path = upload_path
        else:
            find_dataset_document(document_id)

    applied: dict = {}
    if changes:
        try:
            applied = update_manifest_metadata(manifest_path, document_id, changes)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} was not found.",
            ) from exc

    record = _get_or_create_admin_record(document_id, session)
    record.overrides = {**record.overrides, **applied}
    record.updated_at = now_utc()
    record.updated_by = user.user_id
    session.commit()

    log_audit(
        actor=user.user_id,
        action="document.metadata_updated",
        target_type="document",
        target_id=document_id,
        details={"applied": {key: str(value) for key, value in applied.items()}},
    )
    return {
        "status": "updated",
        "document_id": document_id,
        "applied_changes": applied,
        "editable_fields": sorted(MANIFEST_EDITABLE_FIELDS),
    }


@router.put("/documents/{document_id}/relationships")
def replace_relationships(
    document_id: str,
    payload: list[DocumentRelationshipRequest],
    session: DbSession,
    user: AdminUser,
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
    log_audit(
        actor=user.user_id,
        action="document.relationships_updated",
        target_type="document",
        target_id=document_id,
        details={"relationships": relationships},
    )
    return {"status": "updated", "relationships": relationships}


@router.post("/documents/{document_id}/publication")
def update_publication(
    document_id: str,
    payload: PublicationRequest,
    session: DbSession,
    user: AdminUser,
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
            "created_by": user.user_id,
        }
    )
    session.commit()
    log_audit(
        actor=user.user_id,
        action=f"document.{publication_status}",
        target_type="document",
        target_id=document_id,
        details={"version": record.version},
    )
    return {
        "status": publication_status,
        "version": record.version,
        "versions": list(reversed(record.versions_history)),
    }


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    session: DbSession,
    user: AdminUser,
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

    manifest_document = register_upload(
        storage_root(),
        document_id=document_id,
        file_name=safe_name,
        topic=topic,
        content=content,
        source_url=public_url,
    )
    log_audit(
        actor=user.user_id,
        action="document.uploaded",
        target_type="document",
        target_id=document_id,
        details={
            "file_name": safe_name,
            "topic": topic,
            "size_bytes": len(content),
        },
    )
    return {
        "upload_id": upload_id,
        "document_id": document_id,
        "file_name": safe_name,
        "topic": topic,
        "size_bytes": len(content),
        "status": "uploaded",
        "storage_url": public_url,
        "sha256": manifest_document.sha256,
        "manifest_ready": True,
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
                relationship_index=relationship_index_for_manifest(dataset_metadata_path()),
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
        metadata = document.metadata or {}
        if (
            payload.regulation_type
            and metadata.get("regulation_type", "").lower() != payload.regulation_type.lower()
        ):
            continue
        if payload.year is not None and metadata.get("year") != payload.year:
            continue
        if payload.legal_status and document.legal_status != payload.legal_status:
            continue
        results.append(
            {
                "chunk_id": document.chunk_id,
                "document_id": document.document_id,
                "short_title": metadata.get("short_title", document.document_id),
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


@router.get("/settings")
def admin_settings(_: AdminUser) -> dict:
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "admin_email": settings.admin_email,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "vector_store": settings.vector_store,
        "embedding_provider": settings.embedding_provider,
        "llm_provider": settings.llm_provider,
        "session_expires_in_seconds": 3600,
    }


@router.get("/audit-logs")
def audit_logs(
    session: DbSession,
    _: AdminUser,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return list_audit_logs(session, limit=limit)
