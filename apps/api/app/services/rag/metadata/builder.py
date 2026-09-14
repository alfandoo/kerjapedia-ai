"""Index metadata builder with schema validation on write.

Required fields can never silently go missing: validation raises with
the exact absent keys. Two topic layers stay separate — document tags
for filtering, verified chunk tags for ranking signals.
"""

from __future__ import annotations

from app.services.rag.metadata.keywords import detect_language, extract_key_terms
from app.services.rag.metadata.schemas import (
    REQUIRED_INDEX_FIELDS,
    SCHEMA_VERSION,
    TEXT_LIMIT,
    ChunkArtifact,
)


def build_index_metadata(
    *,
    chunk_id: str,
    document_id: str,
    version: int,
    short_title: str,
    regulation_type: str = "",
    number: int = 0,
    year: int = 0,
    issuer: str = "",
    title: str = "",
    topics_doc: list[str] | tuple[str, ...] = (),
    topics_chunk: list[str] | tuple[str, ...] = (),
    segment_kind: str = "substantive",
    legal_status: str = "needs_verification",
    verification_status: str = "pending",
    source_url: str = "",
    local_file: str = "",
    chapter: str | None = None,
    section: str | None = None,
    article: str | None = None,
    paragraph: str | None = None,
    page_start: int = 0,
    page_end: int = 0,
    token_count: int = 0,
    text: str = "",
    retrieval_text: str = "",
    quality_score: float = 0.0,
    ocr_sourced: bool = False,
    language: str | None = None,
    effective_date: str = "",
    freshness_state: str = "due",
    embedding_model: str = "",
    embedding_revision: str = "",
    build_id: str = "",
) -> dict:
    """Build flat index metadata; every value stays Pinecone-compatible."""
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "chunk_id": chunk_id,
        "document_id": document_id,
        "version": version,
        "title": title,
        "short_title": short_title,
        "regulation_type": regulation_type,
        "number": number,
        "year": year,
        "issuer": issuer,
        "topics_doc": list(topics_doc),
        "topics_chunk": list(topics_chunk),
        "segment_kind": segment_kind,
        "legal_status": legal_status,
        "verification_status": verification_status,
        "source_url": source_url,
        "local_file": local_file,
        # Pinecone rejects nulls: legitimately absent labels store as "".
        "chapter": chapter or "",
        "section": section or "",
        "article": article or "",
        "paragraph": paragraph or "",
        "page_start": page_start,
        "page_end": page_end,
        "token_count": token_count,
        "text": text[:TEXT_LIMIT],
        "retrieval_text": (retrieval_text or text)[:TEXT_LIMIT],
        "key_terms": extract_key_terms(retrieval_text or text),
        "quality_score": quality_score,
        "ocr_sourced": ocr_sourced,
        "language": language or detect_language(f"{retrieval_text} {text}"),
        "effective_date": effective_date,
        "freshness_state": freshness_state,
        "embedding_model": embedding_model,
        "embedding_revision": embedding_revision,
        "build_id": build_id,
    }
    return {key: value for key, value in metadata.items() if value is not None}


def validate_index_metadata(metadata: dict) -> list[str]:
    """Required keys absent or None. Empty values (no article, no verified
    topics yet) are legitimate and pass; only structural loss fails."""
    return [key for key in REQUIRED_INDEX_FIELDS if metadata.get(key) is None]


def build_artifact(
    *,
    chunk_id: str,
    document_id: str,
    parent_text: str = "",
    text: str = "",
    retrieval_text: str = "",
    metadata: dict | None = None,
) -> ChunkArtifact:
    """Generator-side record kept out of the vector index."""
    return ChunkArtifact(
        chunk_id=chunk_id,
        document_id=document_id,
        parent_text=parent_text,
        text=text,
        retrieval_text=retrieval_text,
        metadata=dict(metadata or {}),
    )
