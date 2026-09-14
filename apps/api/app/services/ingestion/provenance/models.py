"""Typed provenance grouped by operational ownership."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DocumentProvenance:
    document_id: str
    document_type: str
    document_number: int | str
    year: int
    document_title: str
    regulation_status: str
    source_url: str | None
    source_file: str | None
    file_hash: str


@dataclass(frozen=True)
class StructureProvenance:
    bab: str | None
    bagian: str | None
    paragraf: str | None
    pasal: str | None
    ayat: str | None
    page_start: int
    page_end: int
    section_path: tuple[str, ...]
    legal_node_id: str | None
    amendment_scope: str | None = None


@dataclass(frozen=True)
class ChunkProvenance:
    chunk_id: str
    parent_chunk_id: str | None
    chunk_index: int
    content_hash: str


@dataclass(frozen=True)
class IngestionProvenance:
    ingestion_version: str
    parser_version: str
    chunker_version: str
    embedding_model: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MetadataContext:
    parser_version: str
    chunker_version: str
    embedding_model: str
    created_at: datetime
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.updated_at is not None:
            if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
                raise ValueError("updated_at must be timezone-aware")
            if self.updated_at < self.created_at:
                raise ValueError("updated_at must not precede created_at")
