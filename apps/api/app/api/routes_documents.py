from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.api.dependencies import AdminUser
from app.api.schemas import DocumentSummary, DocumentUpdateRequest
from app.api.utils import find_dataset_document, load_dataset_documents, project_root, storage_root
from app.services.retrieval.store import load_artifact_documents

router = APIRouter(prefix="/documents", tags=["documents"])


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
def list_documents() -> list[DocumentSummary]:
    documents = sorted(
        load_dataset_documents(),
        key=lambda item: (item.year, item.regulation_type, item.number),
        reverse=True,
    )
    return [to_document_summary(document) for document in documents]


@router.get("/{document_id}")
def get_document(document_id: str) -> dict:
    document = find_dataset_document(document_id)
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
    document = find_dataset_document(document_id)
    dataset_root = (project_root() / "dataset").resolve()
    pdf_path = (project_root() / document.local_file).resolve()
    if dataset_root not in pdf_path.parents or pdf_path.suffix.lower() != ".pdf":
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
    document = find_dataset_document(document_id)
    return {
        "status": "accepted",
        "message": "Metadata update is validated but not persisted until admin storage is enabled.",
        "document_id": document.document_id,
        "requested_changes": payload.model_dump(exclude_none=True),
    }
