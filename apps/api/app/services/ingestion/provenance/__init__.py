"""Categorized deterministic metadata and provenance for legal chunks."""

from app.services.ingestion.provenance.builder import (
    METADATA_SCHEMA_VERSION,
    build_provenance_payload,
    enrich_chunk_metadata,
    metadata_sha256,
)
from app.services.ingestion.provenance.legacy import build_legacy_chunk_provenance
from app.services.ingestion.provenance.models import (
    ChunkProvenance,
    DocumentProvenance,
    IngestionProvenance,
    MetadataContext,
    StructureProvenance,
)
from app.services.ingestion.provenance.validation import (
    MetadataValidationError,
    validate_chunk_provenance,
    validate_provenance_payload,
)

__all__ = [
    "METADATA_SCHEMA_VERSION",
    "ChunkProvenance",
    "DocumentProvenance",
    "IngestionProvenance",
    "MetadataContext",
    "MetadataValidationError",
    "StructureProvenance",
    "build_provenance_payload",
    "build_legacy_chunk_provenance",
    "enrich_chunk_metadata",
    "metadata_sha256",
    "validate_chunk_provenance",
    "validate_provenance_payload",
]
