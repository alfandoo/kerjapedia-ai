"""Deterministic generation of categorized legal chunk provenance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any

from app.services.ingestion.domain import Chunk, StructuredLegalDocument, content_sha256
from app.services.ingestion.provenance.models import (
    ChunkProvenance,
    DocumentProvenance,
    IngestionProvenance,
    MetadataContext,
    StructureProvenance,
)

METADATA_SCHEMA_VERSION = "chunk-provenance-v1"


def enrich_chunk_metadata(
    structured: StructuredLegalDocument,
    chunks: tuple[Chunk, ...],
    context: MetadataContext,
) -> tuple[Chunk, ...]:
    """Attach a complete deterministic provenance snapshot to every chunk."""
    document = structured.document
    document_provenance = DocumentProvenance(
        document_id=document.document_id,
        document_type=_required_document_value(
            document.metadata,
            "document_type",
            "regulation_type",
        ),
        document_number=_required_document_value(
            document.metadata,
            "document_number",
            "number",
        ),
        year=int(_required_document_value(document.metadata, "year")),
        document_title=document.title,
        regulation_status=_required_document_value(
            document.metadata,
            "regulation_status",
            "legal_status",
        ),
        source_url=document.source_url,
        source_file=str(document.file_path) if document.file_path else None,
        file_hash=document.file_hash,
    )
    enriched: list[Chunk] = []
    for chunk_index, chunk in enumerate(chunks):
        if chunk.document_id != document.document_id:
            raise ValueError(
                f"Chunk {chunk.chunk_id} belongs to {chunk.document_id}, "
                f"not {document.document_id}"
            )
        structure = StructureProvenance(
            bab=chunk.legal_hierarchy.get("bab"),
            bagian=chunk.legal_hierarchy.get("bagian"),
            paragraf=chunk.legal_hierarchy.get("paragraf"),
            pasal=chunk.legal_hierarchy.get("pasal"),
            ayat=chunk.legal_hierarchy.get("ayat"),
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_path=chunk.section_path,
            legal_node_id=_optional_string(chunk.metadata.get("section_node_id")),
            amendment_scope=chunk.legal_hierarchy.get("amendment_scope"),
        )
        expected_content_hash = content_sha256(chunk.content)
        if chunk.content_hash != expected_content_hash:
            raise ValueError(f"Chunk {chunk.chunk_id} has an invalid content hash")
        chunk_provenance = ChunkProvenance(
            chunk_id=chunk.chunk_id,
            parent_chunk_id=chunk.parent_chunk_id,
            chunk_index=chunk_index,
            content_hash=expected_content_hash,
        )
        ingestion = IngestionProvenance(
            ingestion_version=document.ingestion_version,
            parser_version=context.parser_version,
            chunker_version=context.chunker_version,
            embedding_model=context.embedding_model,
            created_at=context.created_at,
            updated_at=context.updated_at or context.created_at,
        )
        payload = build_provenance_payload(
            document_provenance,
            structure,
            chunk_provenance,
            ingestion,
        )
        enriched.append(replace(chunk, metadata=payload))

    result = tuple(enriched)
    from app.services.ingestion.provenance.validation import validate_chunk_provenance

    validate_chunk_provenance(structured, result)
    return result


def build_provenance_payload(
    document: DocumentProvenance,
    structure: StructureProvenance,
    chunk: ChunkProvenance,
    ingestion: IngestionProvenance,
) -> dict[str, Any]:
    """Build categorized JSON and bind it with a metadata checksum."""
    payload: dict[str, Any] = {
        "schema_version": METADATA_SCHEMA_VERSION,
        "document": asdict(document),
        "structure": {
            **asdict(structure),
            "section_path": list(structure.section_path),
        },
        "chunk": asdict(chunk),
        "ingestion": {
            **asdict(ingestion),
            "created_at": _timestamp(ingestion.created_at),
            "updated_at": _timestamp(ingestion.updated_at),
        },
    }
    payload["chunk"]["metadata_hash"] = metadata_sha256(payload)
    return payload


def metadata_sha256(payload: dict[str, Any]) -> str:
    canonical_payload = _without_metadata_hash(payload)
    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _without_metadata_hash(payload: dict[str, Any]) -> dict[str, Any]:
    copied = {
        category: dict(value) if isinstance(value, dict) else value
        for category, value in payload.items()
    }
    chunk = copied.get("chunk")
    if isinstance(chunk, dict):
        chunk.pop("metadata_hash", None)
    return copied


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Provenance timestamps must be timezone-aware")
    return value.isoformat()


def _required_document_value(metadata: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = metadata.get(name)
        if value is not None and value != "":
            return value
    raise ValueError(f"Document metadata is missing required field: {' or '.join(names)}")


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None
