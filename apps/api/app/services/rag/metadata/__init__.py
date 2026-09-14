"""Index metadata: two topic layers, segment kind, quality, and keys."""

from app.services.rag.metadata.builder import (
    build_artifact,
    build_index_metadata,
    validate_index_metadata,
)
from app.services.rag.metadata.keywords import detect_language, extract_key_terms
from app.services.rag.metadata.schemas import (
    REQUIRED_INDEX_FIELDS,
    SCHEMA_VERSION,
    ChunkArtifact,
)

__all__ = [
    "ChunkArtifact",
    "REQUIRED_INDEX_FIELDS",
    "SCHEMA_VERSION",
    "build_artifact",
    "build_index_metadata",
    "detect_language",
    "extract_key_terms",
    "validate_index_metadata",
]
