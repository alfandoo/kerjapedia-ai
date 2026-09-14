"""Compatibility adapter from normalized chunks to the active persistence schema.

The retrieval and database layers still consume ``schemas.Chunk``.  This
adapter lets the active ingestion pipeline use the structure-aware chunker
without changing that external contract.
"""

from __future__ import annotations

import hashlib

from app.services.ingestion.chunking.chunker import chunk_legal_document
from app.services.ingestion.chunking.models import ChunkingConfig, ChunkingResult
from app.services.ingestion.chunking.tokenizer import Tokenizer
from app.services.ingestion.domain import StructuredLegalDocument
from app.services.ingestion.schemas import Chunk as LegacyChunk
from app.services.ingestion.schemas import DocumentMetadata


def build_legacy_chunks_from_structure(
    document: DocumentMetadata,
    structured: StructuredLegalDocument,
    *,
    tokenizer: Tokenizer,
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
    build_id: str | None,
) -> tuple[list[LegacyChunk], ChunkingResult]:
    """Chunk a legal tree and preserve the legacy retrieval/persistence shape."""
    result = chunk_legal_document(
        structured,
        tokenizer=tokenizer,
        config=ChunkingConfig(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            min_tokens=min(80, target_tokens),
            overlap_tokens=min(overlap_tokens, max(0, target_tokens - 1)),
        ),
    )
    return [
        _to_legacy_chunk(document, chunk, index, build_id)
        for index, chunk in enumerate(result.chunks, start=1)
    ], result


def _to_legacy_chunk(
    document: DocumentMetadata,
    chunk,
    index: int,
    build_id: str | None,
) -> LegacyChunk:
    hierarchy = chunk.legal_hierarchy
    chapter = _prefixed("BAB", hierarchy.get("bab"))
    section_parts = [
        _prefixed("Bagian", hierarchy.get("bagian")),
        _prefixed("Paragraf", hierarchy.get("paragraf")),
    ]
    section = " / ".join(part for part in section_parts if part) or None
    article = _prefixed("Pasal", hierarchy.get("pasal"))
    paragraph = _prefixed("Ayat", _parenthesized(hierarchy.get("ayat")))
    retrieval_text = "\n".join(
        value
        for value in (document.title, *chunk.section_path, chunk.content)
        if value
    )
    # Keep current build-scoped vector IDs while deriving their material from
    # deterministic normalized chunks. This avoids breaking existing releases.
    build_key = build_id.removeprefix("ingb_") if build_id else "legacy"
    chunk_id = f"{document.document_id}-b{build_key}-chunk-{index:05d}"
    checksum = hashlib.sha256(f"{chunk_id}\n{retrieval_text}".encode()).hexdigest()
    return LegacyChunk(
        chunk_id=chunk_id,
        document_id=document.document_id,
        chapter=chapter,
        section=section,
        article=article,
        paragraph=paragraph,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        text=chunk.content,
        token_count=chunk.token_count,
        topics=document.topics,
        legal_status=document.legal_status,
        source_url=document.source_url,
        parent_text=None,
        char_start=0,
        char_end=len(chunk.content),
        build_id=build_id,
        retrieval_text=retrieval_text,
        chunk_type=chunk.chunk_type,
        artifact_checksum=checksum,
    )


def _prefixed(prefix: str, value: str | None) -> str | None:
    return f"{prefix} {value}" if value else None


def _parenthesized(value: str | None) -> str | None:
    return f"({value})" if value else None
