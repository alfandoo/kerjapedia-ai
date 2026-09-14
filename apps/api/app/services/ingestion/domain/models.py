"""Normalized internal records shared by ingestion stages.

These models intentionally contain no persistence, embedding, indexing, or
transport behavior. Later ingestion stages may enrich them without coupling
the parser to those concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.ingestion.domain.diagnostics import ExtractionDiagnostic


@dataclass(frozen=True)
class Page:
    """One source page with raw and cleaned text kept separately."""

    page_number: int
    raw_text: str
    cleaned_text: str
    diagnostics: tuple[ExtractionDiagnostic, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must be one-based and positive")


@dataclass(frozen=True)
class Document:
    """A normalized source document and its ordered pages."""

    document_id: str
    title: str
    source: str
    source_url: str | None
    file_path: Path | None
    file_hash: str
    page_count: int
    metadata: dict[str, Any]
    ingestion_version: str
    pages: tuple[Page, ...] = ()

    def __post_init__(self) -> None:
        if self.page_count < 0:
            raise ValueError("page_count must not be negative")
        if self.pages and len(self.pages) != self.page_count:
            raise ValueError("page_count must match the number of pages")
        page_numbers = tuple(page.page_number for page in self.pages)
        if page_numbers != tuple(sorted(page_numbers)):
            raise ValueError("document pages must be ordered by page_number")
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("document page numbers must be unique")


@dataclass(frozen=True)
class LegalSection:
    """A legal structure node; parent and children are stable identifiers."""

    type: str
    identifier: str
    title: str | None
    text: str
    page_start: int
    page_end: int
    parent: str | None = None
    children: tuple[str, ...] = ()
    order: int = 0
    node_id: str | None = None
    role: str | None = None
    amendment_scope: str | None = None
    # A later node can repeat an earlier provision verbatim in the official
    # source. Keep that occurrence in the legal tree for auditability while
    # allowing downstream indexing to avoid a duplicate vector.
    source_duplicate_of: str | None = None

    def __post_init__(self) -> None:
        if self.page_start < 1:
            raise ValueError("page_start must be positive")
        if self.page_end < self.page_start:
            raise ValueError("page_end must not precede page_start")
        if self.order < 0:
            raise ValueError("order must not be negative")


@dataclass(frozen=True)
class StructuredLegalDocument:
    """One normalized document paired with its ordered legal-section tree."""

    document: Document
    sections: tuple[LegalSection, ...]
    schema_version: str = "legal-structure-v1"

    def __post_init__(self) -> None:
        orders = tuple(section.order for section in self.sections)
        if orders != tuple(sorted(orders)):
            raise ValueError("legal sections must be ordered")
        node_ids = tuple(section.node_id for section in self.sections if section.node_id)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("legal section node IDs must be unique")


@dataclass(frozen=True)
class Chunk:
    """A future retrievable unit without embedding or persistence concerns."""

    chunk_id: str
    document_id: str
    content: str
    page_start: int
    page_end: int
    legal_hierarchy: dict[str, str]
    metadata: dict[str, Any]
    content_hash: str
    parent_chunk_id: str | None = None
    section_path: tuple[str, ...] = ()
    source: str | None = None
    source_url: str | None = None
    token_count: int = 0
    chunk_type: str = "substantive"
    part_number: int = 1
    part_count: int = 1

    def __post_init__(self) -> None:
        if self.page_start < 1:
            raise ValueError("page_start must be positive")
        if self.page_end < self.page_start:
            raise ValueError("page_end must not precede page_start")
        if self.token_count < 0:
            raise ValueError("token_count must not be negative")
        if self.part_number < 1 or self.part_count < self.part_number:
            raise ValueError("chunk part numbering is invalid")
