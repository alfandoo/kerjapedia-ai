from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.dependencies import AdminUser
from app.api.schemas import (
    DocumentRelationshipRequest,
    DocumentUpdateRequest,
    PublicationRequest,
    RetrievalPlaygroundRequest,
)
from app.api.state import now_utc, state
from app.api.utils import (
    dataset_metadata_path,
    find_dataset_document,
    load_dataset_documents,
    storage_root,
)
from app.api.utils import project_root as get_project_root
from app.core.config import settings
from app.services.providers import pinecone_store_from_settings
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.store import load_artifact_documents

router = APIRouter(prefix="/admin", tags=["admin"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def project_root() -> Path:
    return get_project_root()


def _manifest_relationships() -> list[dict]:
    data = json.loads(dataset_metadata_path().read_text(encoding="utf-8"))
    return data.get("relationships", [])


def _default_admin_record(document_id: str, index: int) -> dict:
    relationships = [
        item for item in _manifest_relationships() if item["from_document_id"] == document_id
    ]
    return {
        "publication_status": "published" if index % 3 else "draft",
        "version": 2 if index % 4 else 1,
        "updated_at": now_utc(),
        "updated_by": "Admin",
        "relationships": relationships,
        "versions": [
            {
                "version": 1,
                "status": "draft",
                "created_at": now_utc(),
                "created_by": "System",
            }
        ],
        "overrides": {},
    }


def _admin_record(document_id: str, index: int = 0) -> dict:
    if document_id not in state.document_admin:
        state.document_admin[document_id] = _default_admin_record(document_id, index)
    return state.document_admin[document_id]


def _latest_jobs() -> dict[str, dict]:
    jobs: dict[str, dict] = {}
    for job in sorted(
        state.ingestion_jobs.values(),
        key=lambda item: item["updated_at"],
        reverse=True,
    ):
        jobs.setdefault(job["document_id"], job)
    return jobs


@router.get("/documents")
def list_admin_documents(_: AdminUser) -> dict:
    documents = load_dataset_documents()
    chunks = load_artifact_documents(storage_root())
    chunk_counts: dict[str, int] = {}
    for chunk in chunks:
        chunk_counts[chunk.document_id] = chunk_counts.get(chunk.document_id, 0) + 1
    jobs = _latest_jobs()
    results = []

    for index, document in enumerate(documents):
        record = _admin_record(document.document_id, index)
        job = jobs.get(document.document_id)
        ingestion_status = (
            job["status"]
            if job
            else ("completed" if chunk_counts.get(document.document_id, 0) else "needs_review")
        )
        payload = asdict(document)
        payload.update(record["overrides"])
        payload.update(
            {
                "ingestion_status": ingestion_status,
                "chunk_count": chunk_counts.get(document.document_id, 0),
                "publication_status": record["publication_status"],
                "version": record["version"],
                "updated_at": record["updated_at"],
                "updated_by": record["updated_by"],
                "relationships": record["relationships"],
                "versions": list(reversed(record["versions"])),
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
    _: AdminUser,
) -> dict:
    find_dataset_document(document_id)
    record = _admin_record(document_id)
    changes = payload.model_dump(exclude_none=True)
    record["overrides"].update(changes)
    record["updated_at"] = now_utc()
    return {"status": "updated", "document_id": document_id, "changes": changes}


@router.put("/documents/{document_id}/relationships")
def replace_relationships(
    document_id: str,
    payload: list[DocumentRelationshipRequest],
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
    record = _admin_record(document_id)
    record["relationships"] = relationships
    record["updated_at"] = now_utc()
    return {"status": "updated", "relationships": relationships}


@router.post("/documents/{document_id}/publication")
def update_publication(
    document_id: str,
    payload: PublicationRequest,
    _: AdminUser,
) -> dict:
    find_dataset_document(document_id)
    record = _admin_record(document_id)
    publication_status = "published" if payload.action == "publish" else "draft"
    record["version"] += 1
    record["publication_status"] = publication_status
    record["updated_at"] = now_utc()
    record["versions"].append(
        {
            "version": record["version"],
            "status": publication_status,
            "created_at": record["updated_at"],
            "created_by": "Admin",
        }
    )
    return {
        "status": publication_status,
        "version": record["version"],
        "versions": list(reversed(record["versions"])),
    }


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
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
    destination_dir = project_root() / "storage" / "uploads"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{upload_id}_{safe_name}"
    destination.write_bytes(content)
    document_id = re.sub(r"[^A-Z0-9]+", "-", Path(safe_name).stem.upper()).strip("-")
    uploaded = {
        "upload_id": upload_id,
        "document_id": document_id,
        "file_name": safe_name,
        "topic": topic,
        "size_bytes": len(content),
        "status": "uploaded",
        "created_at": now_utc(),
    }
    state.uploaded_documents.append(uploaded)
    return uploaded


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
