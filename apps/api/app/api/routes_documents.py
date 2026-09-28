from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import file_digest

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse

from app.api.dependencies import AdminUser, DbSession, OptionalUser
from app.api.schemas import DocumentSummary, DocumentUpdateRequest
from app.api.utils import (
    dataset_metadata_path,
    find_dataset_document,
    load_dataset_documents,
    project_root,
    storage_root,
)
from app.models.ingestion import DocumentVersion
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
from app.services.retrieval.governance import load_retrieval_governance
from app.services.retrieval.store import load_artifact_documents


def private_document_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(private_document_response)]
)


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


def document_access(session, user):
    """Only a server-verified admin can preview unpublished artifacts."""
    if user is not None and "admin" in user.roles:
        return None
    return load_retrieval_governance(session, allow_unpublished=False)


def visible_document(document_id, session, access, document=None):
    document = document if document is not None else find_merged_document(document_id)
    if access is None:
        return document
    version = access.eligible_versions.get(document_id)
    row = session.get(DocumentVersion, f"{document_id}-v{version}") if version is not None else None
    # A manifest may already point to an unreviewed replacement upload.
    if row is None or row.sha256 != document.sha256:
        raise HTTPException(status_code=404, detail="Document was not found.")
    return replace(
        document,
        local_file=row.local_file,
        source_url=row.source_url,
        legal_status=row.legal_status,
    )


def visible_chunks(access):
    if access is None:
        return load_artifact_documents(storage_root())
    return load_artifact_documents(
        storage_root(),
        eligible_versions={
            key: version
            for key, version in access.eligible_versions.items()
            if access.eligible_builds.get(f"{key}-v{version}")
        },
        eligible_builds=access.eligible_builds,
    )


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
    session: DbSession,
    user: OptionalUser,
    q: str | None = Query(default=None, max_length=200),
    regulation_type: str | None = Query(default=None, max_length=40),
    year: int | None = Query(default=None, ge=1945, le=2100),
    legal_status: str | None = Query(default=None, max_length=40),
    topic: str | None = Query(default=None, max_length=40),
) -> list[DocumentSummary]:
    access = document_access(session, user)
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

    result = []
    for document in documents:
        try:
            document = visible_document(document.document_id, session, access, document)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            continue
        if matches(document):
            result.append(to_document_summary(document))
    return result


@router.get("/{document_id}")
def get_document(document_id: str, session: DbSession, user: OptionalUser) -> dict:
    access = document_access(session, user)
    document = visible_document(document_id, session, access)
    chunks = [item for item in visible_chunks(access) if item.document_id == document_id]
    payload = asdict(document)
    if access is not None:
        for key in ("local_file", "sha256", "file_name"):
            payload.pop(key, None)
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
def get_document_pdf(document_id: str, session: DbSession, user: OptionalUser) -> FileResponse:
    access = document_access(session, user)
    document = visible_document(document_id, session, access)
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
    if access is not None:
        with pdf_path.open("rb") as source:
            if file_digest(source, "sha256").hexdigest() != document.sha256:
                raise HTTPException(status_code=404, detail="Dataset PDF was not found.")
    return FileResponse(
        pdf_path,
        headers={"Cache-Control": "private, no-store", "Vary": "Authorization"},
        media_type="application/pdf",
        filename=document.file_name,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/citations/{chunk_id}")
def get_citation(document_id: str, chunk_id: str, session: DbSession, user: OptionalUser) -> dict:
    access = document_access(session, user)
    visible_document(document_id, session, access)
    chunks = [
        item
        for item in visible_chunks(access)
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
        "metadata": chunk.metadata
        if access is None
        else {
            key: value
            for key, value in chunk.metadata.items()
            if key
            in {
                "title",
                "short_title",
                "regulation_type",
                "number",
                "year",
                "issuer",
                "topics",
                "legal_status",
                "source_url",
            }
        },
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
