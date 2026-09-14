"""Fail-closed validation for chunk metadata and source provenance."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.services.ingestion.domain import Chunk, StructuredLegalDocument, content_sha256
from app.services.ingestion.provenance.builder import (
    METADATA_SCHEMA_VERSION,
    metadata_sha256,
)


class MetadataValidationError(ValueError):
    def __init__(self, issues: Sequence[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(self.issues))


_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)


def validate_chunk_provenance(
    structured: StructuredLegalDocument,
    chunks: Sequence[Chunk],
) -> None:
    """Validate identity, hierarchy, hashes, ordering, and page provenance."""
    issues: list[str] = []
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    duplicates = sorted(
        chunk_id for chunk_id, count in Counter(chunk_ids).items() if count > 1
    )
    if duplicates:
        issues.append("duplicate chunk_id values: " + ", ".join(duplicates))
    known_ids = set(chunk_ids)
    document = structured.document
    page_numbers = {page.page_number for page in document.pages}

    for expected_index, chunk in enumerate(chunks):
        prefix = f"chunk {chunk.chunk_id}"
        if chunk.document_id != document.document_id:
            issues.append(f"{prefix}: document_id does not match the structured document")
        if chunk.page_start > chunk.page_end:
            issues.append(f"{prefix}: page_start must not exceed page_end")
        if page_numbers and (
            chunk.page_start not in page_numbers or chunk.page_end not in page_numbers
        ):
            issues.append(f"{prefix}: page range is outside the source document")
        if chunk.content_hash != content_sha256(chunk.content):
            issues.append(f"{prefix}: content_hash does not match normalized content")
        if chunk.parent_chunk_id and chunk.parent_chunk_id not in known_ids:
            issues.append(f"{prefix}: parent_chunk_id does not reference a stored chunk")

        metadata = chunk.metadata
        if metadata.get("schema_version") != METADATA_SCHEMA_VERSION:
            issues.append(f"{prefix}: unsupported metadata schema version")
            continue
        document_metadata = _mapping(metadata.get("document"))
        structure_metadata = _mapping(metadata.get("structure"))
        chunk_metadata = _mapping(metadata.get("chunk"))
        ingestion_metadata = _mapping(metadata.get("ingestion"))
        if document_metadata.get("document_id") != document.document_id:
            issues.append(f"{prefix}: metadata document_id does not match")
        required_document_fields = (
            "document_type",
            "document_number",
            "year",
            "document_title",
            "regulation_status",
            "file_hash",
        )
        missing = [
            field
            for field in required_document_fields
            if document_metadata.get(field) in {None, ""}
        ]
        if missing:
            issues.append(f"{prefix}: missing document provenance: {', '.join(missing)}")
        if not document_metadata.get("source_url") and not document_metadata.get(
            "source_file"
        ):
            issues.append(f"{prefix}: source_url or source_file is required")
        _validate_file_hash(document_metadata.get("file_hash"), prefix, issues)
        if chunk_metadata.get("chunk_id") != chunk.chunk_id:
            issues.append(f"{prefix}: metadata chunk_id does not match")
        if chunk_metadata.get("chunk_index") != expected_index:
            issues.append(f"{prefix}: chunk_index is not deterministic document order")
        if chunk_metadata.get("content_hash") != chunk.content_hash:
            issues.append(f"{prefix}: metadata content_hash does not match")
        if chunk_metadata.get("parent_chunk_id") != chunk.parent_chunk_id:
            issues.append(f"{prefix}: metadata parent_chunk_id does not match")
        if structure_metadata.get("page_start") != chunk.page_start:
            issues.append(f"{prefix}: metadata page_start does not match")
        if structure_metadata.get("page_end") != chunk.page_end:
            issues.append(f"{prefix}: metadata page_end does not match")
        if structure_metadata.get("section_path") != list(chunk.section_path):
            issues.append(f"{prefix}: metadata section_path does not match")
        if not ingestion_metadata.get("parser_version"):
            issues.append(f"{prefix}: parser_version is required")
        if not ingestion_metadata.get("chunker_version"):
            issues.append(f"{prefix}: chunker_version is required")
        if not ingestion_metadata.get("embedding_model"):
            issues.append(f"{prefix}: embedding_model is required")
        _validate_timestamps(ingestion_metadata, prefix, issues)
        if chunk_metadata.get("metadata_hash") != metadata_sha256(metadata):
            issues.append(f"{prefix}: metadata_hash does not match provenance")

    if issues:
        raise MetadataValidationError(issues)


def validate_provenance_payload(
    payload: dict[str, Any],
    *,
    content: str,
    expected_document_id: str,
) -> None:
    """Validate a serialized payload before a persistence adapter stores it."""
    issues: list[str] = []
    document = _mapping(payload.get("document"))
    structure = _mapping(payload.get("structure"))
    chunk = _mapping(payload.get("chunk"))
    ingestion = _mapping(payload.get("ingestion"))
    if payload.get("schema_version") != METADATA_SCHEMA_VERSION:
        issues.append("unsupported metadata schema version")
    if document.get("document_id") != expected_document_id:
        issues.append("document_id does not match the persistence target")
    if not document.get("source_url") and not document.get("source_file"):
        issues.append("source_url or source_file is required")
    _validate_file_hash(document.get("file_hash"), "document", issues)
    page_start = _integer(structure.get("page_start"))
    page_end = _integer(structure.get("page_end"))
    if page_start is None or page_end is None or page_start < 1 or page_start > page_end:
        issues.append("page_start must not exceed page_end")
    if chunk.get("content_hash") != content_sha256(content):
        issues.append("content_hash does not match normalized chunk content")
    _validate_timestamps(ingestion, "ingestion", issues)
    if chunk.get("metadata_hash") != metadata_sha256(payload):
        issues.append("metadata_hash does not match provenance")
    if issues:
        raise MetadataValidationError(issues)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _validate_file_hash(value: object, prefix: str, issues: list[str]) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        issues.append(f"{prefix}: file_hash must be a 64-character SHA-256 digest")


def _validate_timestamps(
    ingestion: dict[str, Any],
    prefix: str,
    issues: list[str],
) -> None:
    parsed: dict[str, datetime] = {}
    for field in ("created_at", "updated_at"):
        value = ingestion.get(field)
        try:
            timestamp = datetime.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            timestamp = None
        if timestamp is None or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            issues.append(f"{prefix}: {field} must be a timezone-aware ISO timestamp")
        else:
            parsed[field] = timestamp
    if (
        "created_at" in parsed
        and "updated_at" in parsed
        and parsed["updated_at"] < parsed["created_at"]
    ):
        issues.append(f"{prefix}: updated_at precedes created_at")
