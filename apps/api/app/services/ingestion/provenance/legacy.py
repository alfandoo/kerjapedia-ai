"""Compatibility adapter for the active v2 ingestion persistence path."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.services.ingestion.domain import content_sha256
from app.services.ingestion.provenance.builder import build_provenance_payload
from app.services.ingestion.provenance.models import (
    ChunkProvenance,
    DocumentProvenance,
    IngestionProvenance,
    StructureProvenance,
)
from app.services.ingestion.provenance.validation import validate_provenance_payload
from app.services.ingestion.schemas import Chunk, DocumentMetadata

_AYAT_RE = re.compile(r"Ayat\s*\(([^)]+)\)", re.IGNORECASE)


def build_legacy_chunk_provenance(
    document: DocumentMetadata,
    chunk: Chunk,
    *,
    chunk_index: int,
    ingestion_version: str,
    parser_version: str,
    chunker_version: str,
    embedding_model: str,
    created_at: datetime,
    updated_at: datetime,
) -> dict[str, Any]:
    """Map legacy flat chunk fields to the categorized v1 provenance schema."""
    bagian, paragraf = _legacy_section_parts(chunk.section)
    structure_path = tuple(
        value
        for value in (
            chunk.chapter,
            bagian,
            paragraf,
            chunk.article,
            chunk.paragraph,
        )
        if value
    )
    content_hash = content_sha256(chunk.text)
    payload = build_provenance_payload(
        DocumentProvenance(
            document_id=document.document_id,
            document_type=document.regulation_type,
            document_number=document.number,
            year=document.year,
            document_title=document.title,
            regulation_status=document.legal_status,
            source_url=document.source_url,
            source_file=document.local_file,
            file_hash=document.sha256,
        ),
        StructureProvenance(
            bab=_strip_prefix(chunk.chapter, "BAB "),
            bagian=_strip_prefix(bagian, "Bagian "),
            paragraf=_strip_prefix(paragraf, "Paragraf "),
            pasal=_strip_prefix(chunk.article, "Pasal "),
            ayat=_legacy_ayat(chunk.paragraph),
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_path=structure_path,
            legal_node_id=None,
        ),
        ChunkProvenance(
            chunk_id=chunk.chunk_id,
            parent_chunk_id=None,
            chunk_index=chunk_index,
            content_hash=content_hash,
        ),
        IngestionProvenance(
            ingestion_version=ingestion_version,
            parser_version=parser_version,
            chunker_version=chunker_version,
            embedding_model=embedding_model,
            created_at=created_at,
            updated_at=updated_at,
        ),
    )
    validate_provenance_payload(
        payload,
        content=chunk.text,
        expected_document_id=document.document_id,
    )
    return payload


def _legacy_section_parts(section: str | None) -> tuple[str | None, str | None]:
    parts = [part.strip() for part in (section or "").split("/") if part.strip()]
    bagian = next((part for part in parts if part.casefold().startswith("bagian ")), None)
    paragraf = next(
        (part for part in parts if part.casefold().startswith("paragraf ")),
        None,
    )
    return bagian, paragraf


def _legacy_ayat(paragraph: str | None) -> str | None:
    match = _AYAT_RE.search(paragraph or "")
    return match.group(1).strip() if match else None


def _strip_prefix(value: str | None, prefix: str) -> str | None:
    if not value:
        return None
    return value[len(prefix) :].strip() if value.casefold().startswith(prefix.casefold()) else value
