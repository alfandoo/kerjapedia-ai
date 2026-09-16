from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any

from app.services.ingestion.schemas import (
    Chunk,
    EmbeddedChunk,
    ExtractedPage,
    LegalSegment,
)

HEADING_ONLY_RE = re.compile(
    r"^\s*(?:BAB\s+[IVXLCDM]+[A-Z]?|Bagian\s+\S+(?:\s+\S+){0,3}|"
    r"Paragraf\s+\S+(?:\s+\S+){0,3}|Pasal\s+\d+[A-Z]?)\s*$",
    re.IGNORECASE,
)
KNOWN_MARGIN_NOISE_RE = re.compile(
    r"(?im)^\s*(?:PRESIDEN\s+REPUBLIK\s+INDONESIA|SK\s+No\.|"
    r"www\.peraturan\.go\.id|jdih\.|-?\s*\d+\s*-?)\s*$"
)


def is_heading_only(text: str) -> bool:
    return HEADING_ONLY_RE.fullmatch(text.strip()) is not None


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_quality_report(
    pages: list[ExtractedPage],
    chunks: list[Chunk],
    embedded_chunks: list[EmbeddedChunk],
    *,
    expected_dimension: int,
    max_chunk_tokens: int = 550,
    segments: list[LegalSegment] | None = None,
) -> dict[str, Any]:
    unresolved_pages = [
        page.page_number
        for page in pages
        if page.disposition is None
        and (
            page.requires_ocr
            or page.quality_score < 0.65
            or not page.text.strip()
            or page.table_count > 0
        )
    ]
    retrieval_texts = [chunk.retrieval_text or chunk.text for chunk in chunks]
    heading_only = [
        chunk.chunk_id
        for chunk in chunks
        if chunk.chunk_type == "heading" or is_heading_only(chunk.text)
    ]
    margin_noise = [
        chunk.chunk_id
        for chunk, retrieval_text in zip(chunks, retrieval_texts, strict=True)
        if KNOWN_MARGIN_NOISE_RE.search(retrieval_text)
    ]
    duplicate_hashes = [
        checksum
        for checksum, count in Counter(
            text_sha256(text) for text in retrieval_texts
        ).items()
        if count > 1
    ]
    dense_dimensions = [len(item.embedding) for item in embedded_chunks]
    dense_norms = [
        math.sqrt(sum(float(value) * float(value) for value in item.embedding))
        for item in embedded_chunks
    ]
    sparse_count = sum(bool(item.sparse_embedding) for item in embedded_chunks)
    article_chunks = [chunk for chunk in chunks if chunk.article]
    detected_articles = {
        segment.article for segment in (segments or []) if segment.article
    }
    chunk_articles = {chunk.article for chunk in article_chunks}
    gates = {
        "no_unresolved_pages": not unresolved_pages,
        "no_heading_only_embeddings": not heading_only,
        "no_known_margin_noise": not margin_noise,
        "no_duplicate_retrieval_text": not duplicate_hashes,
        "chunk_count_matches_embeddings": len(chunks) == len(embedded_chunks),
        "max_chunk_tokens": all(
            0 < chunk.token_count <= max_chunk_tokens
            for chunk in chunks
        ),
        "detected_articles_present": bool(detected_articles),
        "detected_article_coverage": detected_articles.issubset(chunk_articles),
        "dense_dimension": bool(dense_dimensions)
        and all(value == expected_dimension for value in dense_dimensions),
        "dense_normalized": bool(dense_norms)
        and all(abs(value - 1.0) <= 0.02 for value in dense_norms),
        "native_sparse_complete": sparse_count == len(chunks) and bool(chunks),
        "page_provenance": all(
            chunk.page_start > 0 and chunk.page_end >= chunk.page_start
            for chunk in chunks
        ),
        "legal_path_for_article_chunks": all(chunk.article for chunk in article_chunks),
    }
    # Advisory gates: quality concerns that warn but must not block publication.
    # - native_sparse_complete: dense-only embeddings still retrieve fine.
    # - no_known_margin_noise / no_heading_only_embeddings / no_duplicate_retrieval_text:
    #   cosmetic extraction artifacts that do not corrupt retrieval correctness.
    # - no_unresolved_pages: legal documents often carry annex pages (tables,
    #   organizational charts, scan artifacts) that legitimately have no
    #   extractable text; OCRed content is preserved where it exists.
    non_blocking_gates = {
        "native_sparse_complete",
        "no_known_margin_noise",
        "no_heading_only_embeddings",
        "no_duplicate_retrieval_text",
        "no_unresolved_pages",
    }
    blocking = {
        key: value for key, value in gates.items() if key not in non_blocking_gates
    }
    warnings: list[str] = []
    for key in sorted(non_blocking_gates):
        if key in gates and not gates[key]:
            warnings.append(f"{key} gagal — advisory, tidak memblokir publish.")
    return {
        "status": "passed" if all(blocking.values()) else "review_required",
        "gates": gates,
        "warnings": warnings,
        "pages": {
            "count": len(pages),
            "empty": [page.page_number for page in pages if not page.text.strip()],
            "ocr_required": [page.page_number for page in pages if page.requires_ocr],
            "unresolved": unresolved_pages,
            "tables_detected": sum(page.table_count for page in pages),
            "margin_lines_removed": sum(
                len(page.removed_margin_lines) for page in pages
            ),
        },
        "chunks": {
            "count": len(chunks),
            "article_count": len(chunk_articles),
            "detected_article_count": len(detected_articles),
            "missing_articles": sorted(detected_articles - chunk_articles),
            "heading_only_ids": heading_only,
            "margin_noise_ids": margin_noise,
            "duplicate_retrieval_text_hashes": duplicate_hashes,
            "under_80_tokens": sum(chunk.token_count < 80 for chunk in chunks),
            "maximum_tokens": max((chunk.token_count for chunk in chunks), default=0),
        },
        "embeddings": {
            "count": len(embedded_chunks),
            "dense_dimension": dense_dimensions[0] if dense_dimensions else 0,
            "native_sparse_count": sparse_count,
        },
    }


def artifact_manifest_entry(path: str, content: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
