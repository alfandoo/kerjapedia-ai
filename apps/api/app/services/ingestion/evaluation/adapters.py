from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from app.services.ingestion.domain import Chunk, Document
from app.services.ingestion.evaluation.evaluator import evaluate_ingestion
from app.services.ingestion.evaluation.models import (
    DocumentIngestionEvaluation,
    EmbeddingEvaluationInput,
    IngestionEvaluationThresholds,
)
from app.services.ingestion.pdf_extractor import from_legacy_extracted_page
from app.services.ingestion.schemas import (
    Chunk as ActiveChunk,
)
from app.services.ingestion.schemas import (
    DocumentMetadata,
    EmbeddedChunk,
    ExtractedPage,
)
from app.services.ingestion.structure import parse_legal_sections


def evaluate_active_ingestion(
    document: DocumentMetadata,
    pages: Sequence[ExtractedPage],
    chunks: Sequence[ActiveChunk],
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    project_root: Path,
    ingestion_version: str,
    document_version: int,
    build_id: str,
    expected_dimension: int,
    expected_page_count: int | None = None,
    duration_seconds: float = 0.0,
    file_readable: bool = True,
    source_error: str | None = None,
    embedding_input: EmbeddingEvaluationInput | None = None,
    thresholds: IngestionEvaluationThresholds | None = None,
) -> DocumentIngestionEvaluation:
    """Adapt the active v2 schemas into the normalized evaluation contract."""
    normalized_pages = tuple(from_legacy_extracted_page(page) for page in pages)
    normalized_document = Document(
        document_id=document.document_id,
        title=document.title,
        source=document.source_name,
        source_url=document.source_url,
        file_path=project_root / document.local_file,
        file_hash=document.sha256,
        page_count=len(normalized_pages),
        metadata={
            "regulation_type": document.regulation_type,
            "number": document.number,
            "year": document.year,
            "legal_status": document.legal_status,
        },
        ingestion_version=ingestion_version,
        pages=normalized_pages,
    )
    sections = parse_legal_sections(
        document.document_id,
        normalized_pages,
        document_title=document.title,
    )
    normalized_chunks = tuple(
        _normalized_chunk(document, chunk) for chunk in chunks
    )
    attempted_ids = tuple(chunk.chunk_id for chunk in chunks)
    succeeded_ids = tuple(item.chunk.chunk_id for item in embedded_chunks)
    dimension_mismatch_ids = tuple(
        item.chunk.chunk_id
        for item in embedded_chunks
        if len(item.embedding) != expected_dimension
    )
    models = {item.embedding_model for item in embedded_chunks}
    revisions = {item.embedding_revision for item in embedded_chunks}
    embedding = embedding_input or EmbeddingEvaluationInput(
        attempted_ids=attempted_ids,
        succeeded_ids=succeeded_ids,
        failed_ids=tuple(sorted(set(attempted_ids) - set(succeeded_ids))),
        dimension_mismatch_ids=dimension_mismatch_ids,
        model=next(iter(models)) if len(models) == 1 else None,
        revision=next(iter(revisions)) if len(revisions) == 1 else None,
        expected_dimension=expected_dimension,
        evaluated=True,
    )
    return evaluate_ingestion(
        normalized_document,
        sections,
        normalized_chunks,
        embedding=embedding,
        thresholds=thresholds,
        file_readable=file_readable,
        source_error=source_error,
        expected_page_count=(
            len(pages) if expected_page_count is None else expected_page_count
        ),
        document_version=document_version,
        build_id=build_id,
        duration_seconds=duration_seconds,
    )


def _normalized_chunk(document: DocumentMetadata, chunk: ActiveChunk) -> Chunk:
    content_hash = hashlib.sha256(chunk.text.encode()).hexdigest()
    hierarchy: dict[str, str] = {}
    if chunk.chapter:
        hierarchy["bab"] = _identifier(chunk.chapter, r"(?i)^BAB\s+")
    if chunk.section:
        if re.match(r"(?i)^Bagian\s+", chunk.section):
            hierarchy["bagian"] = _identifier(chunk.section, r"(?i)^Bagian\s+")
        elif re.match(r"(?i)^Paragraf\s+", chunk.section):
            hierarchy["paragraf"] = _identifier(chunk.section, r"(?i)^Paragraf\s+")
        else:
            hierarchy["section"] = chunk.section
    if chunk.article:
        hierarchy["pasal"] = _identifier(chunk.article, r"(?i)^Pasal\s+")
    if chunk.paragraph:
        value = _identifier(chunk.paragraph, r"(?i)^Ayat\s+")
        hierarchy["ayat"] = value.strip("()")
    return Chunk(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        content=chunk.text,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        legal_hierarchy=hierarchy,
        metadata={
            "source": document.source_name,
            "build_id": chunk.build_id,
            "artifact_checksum": chunk.artifact_checksum,
        },
        content_hash=content_hash,
        section_path=tuple(
            value
            for value in (
                chunk.chapter,
                chunk.section,
                chunk.article,
                chunk.paragraph,
            )
            if value
        ),
        source=document.source_name,
        source_url=chunk.source_url,
        token_count=chunk.token_count,
        chunk_type=chunk.chunk_type,
    )


def _identifier(value: str, prefix_pattern: str) -> str:
    return re.sub(prefix_pattern, "", value).strip()
