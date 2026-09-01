from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    title: str
    short_title: str
    regulation_type: str
    number: int
    year: int
    issuer: str
    topics: list[str]
    legal_status: str
    source_name: str
    source_url: str
    local_file: str
    file_name: str
    size_bytes: int
    sha256: str
    verification_status: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentMetadata:
        return cls(
            document_id=data["document_id"],
            title=data["title"],
            short_title=data["short_title"],
            regulation_type=data["regulation_type"],
            number=int(data["number"]),
            year=int(data["year"]),
            issuer=data["issuer"],
            topics=list(data["topics"]),
            legal_status=data["legal_status"],
            source_name=data["source_name"],
            source_url=data["source_url"],
            local_file=data["local_file"],
            file_name=data["file_name"],
            size_bytes=int(data["size_bytes"]),
            sha256=data["sha256"],
            verification_status=data["verification_status"],
        )


@dataclass(frozen=True)
class FileValidationResult:
    path: Path
    is_pdf: bool
    size_bytes: int
    sha256: str
    duplicate_document_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    text_length: int
    requires_ocr: bool
    quality_score: float = 1.0
    quality_flags: list[str] = field(default_factory=list)
    raw_text: str | None = None
    rotation: int = 0
    table_count: int = 0
    removed_margin_lines: list[str] = field(default_factory=list)
    disposition: str | None = None


@dataclass(frozen=True)
class LegalSegment:
    segment_id: str
    document_id: str
    chapter: str | None
    section: str | None
    article: str | None
    paragraph: str | None
    page_start: int
    page_end: int
    text: str
    segment_type: str = "substantive"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    chapter: str | None
    section: str | None
    article: str | None
    paragraph: str | None
    page_start: int
    page_end: int
    text: str
    token_count: int
    topics: list[str]
    legal_status: str
    source_url: str
    parent_text: str | None = None
    char_start: int = 0
    char_end: int = 0
    build_id: str | None = None
    retrieval_text: str | None = None
    chunk_type: str = "substantive"
    artifact_checksum: str | None = None


@dataclass(frozen=True)
class EmbeddedChunk:
    chunk: Chunk
    embedding_model: str
    embedding: list[float]
    sparse_embedding: dict[int, float] | None = None
    embedding_revision: str = "unversioned"
    retrieval_text_sha256: str | None = None


@dataclass(frozen=True)
class IngestionResult:
    document_id: str
    version: int
    status: str
    artifacts: dict[str, str]
    chunk_count: int
    pages_processed: int
    requires_review: bool
    warnings: list[str]
    build_id: str | None = None
    config_hash: str | None = None
    quality_report: dict[str, Any] = field(default_factory=dict)
    artifact_manifest: dict[str, Any] = field(default_factory=dict)
