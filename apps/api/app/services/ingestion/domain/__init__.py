"""Normalized, provider-independent ingestion domain models."""

from app.services.ingestion.domain.diagnostics import ExtractionDiagnostic
from app.services.ingestion.domain.identity import content_sha256, normalize_chunk_content
from app.services.ingestion.domain.models import (
    Chunk,
    Document,
    LegalSection,
    Page,
    StructuredLegalDocument,
)

__all__ = [
    "Chunk",
    "Document",
    "ExtractionDiagnostic",
    "LegalSection",
    "Page",
    "StructuredLegalDocument",
    "content_sha256",
    "normalize_chunk_content",
]
