"""Metadata records: index-facing versus artifact-side.

The vector index carries what retrieval needs (signals, filters,
citations, quality). Bulky generator context (``parent_text``) stays in
the artifact store — never in the index.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = 2

# Flat Pinecone-compatible value types only: str | int | float | bool.
REQUIRED_INDEX_FIELDS: tuple[str, ...] = (
    "schema_version",
    "chunk_id",
    "document_id",
    "version",
    "short_title",
    "topics_chunk",
    "segment_kind",
    "legal_status",
    "source_url",
    "article",
    "text",
    "retrieval_text",
    "key_terms",
    "quality_score",
    "ocr_sourced",
    "language",
    "effective_date",
    "freshness_state",
    "embedding_model",
    "embedding_revision",
)

TEXT_LIMIT = 8000


@dataclass(frozen=True)
class ChunkArtifact:
    """Generator-side record: full context that must not bloat the index."""

    chunk_id: str
    document_id: str
    parent_text: str = ""
    text: str = ""
    retrieval_text: str = ""
    metadata: dict = field(default_factory=dict)
