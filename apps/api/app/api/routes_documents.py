from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.dependencies import AdminUser
from app.api.schemas import DocumentSummary, DocumentUpdateRequest
from app.api.utils import (
    dataset_metadata_path,
    find_dataset_document,
    load_dataset_documents,
    project_root,
    storage_root,
)
from app.services.ingestion.manifest_updater import (
    MANIFEST_EDITABLE_FIELDS,
    manifest_contains,
    update_manifest_metadata,
)
from app.services.ingestion.metadata import find_document
from app.services.ingestion.uploads import (
    load_uploads_manifest,
    merge_documents,
    uploads_manifest_path,
)
from app.services.retrieval.store import load_artifact_documents

router = APIRouter(prefix="/documents", tags=["documents"])


def merged_documents():
    return merge_documents(load_dataset_documents(), load_uploads_manifest(storage_root()))


def find_merged_document(document_id: str):
    try:
        return find_document(merged_documents(), document_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} was not found.",
        ) from exc


def to_document_summary(document) -> DocumentSummary:
    pdf_url = f"/documents/{document.document_id}/pdf"
    return DocumentSummary(
        document_id=document.document_id,
        title=document.title,
        short_title=document.short_title,
        regulation_type=document.regulation_type,
        number=document.number,
        year=document.year,
        legal_status=document.legal_status,
        topics=document.topics,
        source_url=document.source_url,
        pdf_url=pdf_url,
    )


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    q: str | None = Query(default=None, max_length=200),
    regulation_type: str | None = Query(default=None, max_length=40),
    year: int | None = Query(default=None, ge=1945, le=2100),
    legal_status: str | None = Query(default=None, max_length=40),
    topic: str | None = Query(default=None, max_length=40),
) -> list[DocumentSummary]:
    documents = sorted(
        merged_documents(),
        key=lambda item: (item.year, item.regulation_type, item.number),
        reverse=True,
    )

    def matches(document) -> bool:
        if q:
            haystack = " ".join(
                [
                    document.title,
                    document.short_title,
                    document.document_id,
                    " ".join(document.topics or []),
                ]
            ).lower()
            if q.lower() not in haystack:
                return False
        if regulation_type and document.regulation_type.lower() != regulation_type.lower():
            return False
        if year is not None and document.year != year:
            return False
        if legal_status and document.legal_status.lower() != legal_status.lower():
            return False
        if topic and topic not in (document.topics or []):
            return False
        return True

    return [to_document_summary(document) for document in documents if matches(document)]


@router.get("/{document_id}")
def get_document(document_id: str) -> dict:
    document = find_merged_document(document_id)
    chunks = [
        item for item in load_artifact_documents(storage_root()) if item.document_id == document_id
    ]
    payload = asdict(document)
    payload["chunk_count"] = len(chunks)
    payload["available_chunks"] = [
        {
            "chunk_id": chunk.chunk_id,
            "article": chunk.article,
            "paragraph": chunk.paragraph,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
        }
        for chunk in chunks[:50]
    ]
    return payload


@router.get("/{document_id}/pdf", response_class=FileResponse)
def get_document_pdf(document_id: str) -> FileResponse:
    document = find_merged_document(document_id)
    dataset_root = (project_root() / "dataset").resolve()
    uploads_root = (project_root() / "storage" / "ingestion" / "uploads").resolve()
    pdf_path = (project_root() / document.local_file).resolve()
    allowed = dataset_root in pdf_path.parents or uploads_root in pdf_path.parents
    if not allowed or pdf_path.suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset PDF was not found.",
        )
    if not pdf_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset PDF was not found.",
        )
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=document.file_name,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/citations/{chunk_id}")
def get_citation(document_id: str, chunk_id: str) -> dict:
    chunks = [
        item
        for item in load_artifact_documents(storage_root())
        if item.document_id == document_id and item.chunk_id == chunk_id
    ]
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Citation chunk was not found.",
        )
    chunk = chunks[0]
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "article": chunk.article,
        "paragraph": chunk.paragraph,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "quote": chunk.text,
        "source_url": chunk.source_url,
        "metadata": chunk.metadata,
    }


@router.patch("/{document_id}")
def update_document_metadata(
    document_id: str,
    payload: DocumentUpdateRequest,
    _: AdminUser,
) -> dict:
    dataset_path = dataset_metadata_path()
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No editable fields were provided.",
        )

    manifest_path = dataset_path
    if not manifest_contains(manifest_path, document_id):
        upload_path = uploads_manifest_path(storage_root())
        if manifest_contains(upload_path, document_id):
            manifest_path = upload_path
        else:
            find_dataset_document(document_id)

    try:
        applied = update_manifest_metadata(manifest_path, document_id, changes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} was not found.",
        ) from exc

    if not applied:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No editable fields were provided.",
        )
    return {
        "status": "updated",
        "document_id": document_id,
        "applied_changes": applied,
        "editable_fields": sorted(MANIFEST_EDITABLE_FIELDS),
    }
