"""Intake: load, validate early, register as a collection record.

One entry point per source kind. Every path ends in a
``(CollectedDocument, EligibilityVerdict)`` pair — the pipeline never
receives unvalidated bytes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.services.rag.collection.collector import collect_document
from app.services.rag.collection.schemas import (
    CollectedDocument,
    EligibilityVerdict,
)
from app.services.rag.collection.sources import FetchedFile
from app.services.rag.loading.loaders import (
    BytesLoader,
    LocalFileLoader,
    sanitize_file_name,
    sanitize_identifier,
)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _limited(content: bytes, field: str = "upload") -> bytes:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"{field} exceeds {MAX_UPLOAD_BYTES} bytes ({len(content)})."
        )
    return content


def intake_local_file(
    path: Path,
    *,
    document_id: str,
    title: str,
    source_id: str,
    source_url: str = "",
    collected_at: datetime | None = None,
) -> tuple[CollectedDocument, EligibilityVerdict]:
    """Intake a curated on-disk file (read-only, never copied)."""
    sanitize_identifier(document_id)
    loaded = LocalFileLoader().load(path.as_posix())
    document, verdict = collect_document(
        loaded.path,
        document_id=document_id,
        title=title,
        source_id=source_id,
        source_url=source_url,
        origin="curated",
        collected_at=collected_at,
    )
    return document, verdict


def intake_upload(
    content: bytes,
    *,
    store_root: Path,
    document_id: str,
    title: str,
    file_name: str,
    source_id: str,
    source_url: str = "",
    collected_at: datetime | None = None,
) -> tuple[CollectedDocument, EligibilityVerdict]:
    """Intake admin-uploaded bytes: store atomically, validate at intake."""
    sanitize_identifier(document_id)
    sanitize_file_name(file_name)
    loaded = BytesLoader(store_root, "upload").load(
        document_id, _limited(content, "upload")
    )
    document, verdict = collect_document(
        loaded.path,
        document_id=document_id,
        title=title,
        source_id=source_id,
        source_url=source_url,
        origin="upload",
        collected_at=collected_at,
    )
    return document, verdict


def intake_connector_file(
    fetched: FetchedFile,
    *,
    store_root: Path,
    registry_source_id: str,
    document_id: str,
    title: str,
    collected_at: datetime | None = None,
) -> tuple[CollectedDocument, EligibilityVerdict]:
    """Intake a file delivered by a scheduled connector."""
    sanitize_identifier(document_id)
    loaded = BytesLoader(store_root, "connector").load(
        document_id, _limited(fetched.content, "connector file")
    )
    document, verdict = collect_document(
        loaded.path,
        document_id=document_id,
        title=title,
        source_id=registry_source_id,
        source_url=fetched.source_url,
        origin="connector",
        collected_at=collected_at,
    )
    return document, verdict
