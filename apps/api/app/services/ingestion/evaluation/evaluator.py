from __future__ import annotations

import hashlib
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict

from app.services.ingestion.domain import Chunk, Document, LegalSection, Page
from app.services.ingestion.evaluation.models import (
    DocumentIngestionEvaluation,
    EmbeddingEvaluationInput,
    EvaluationFinding,
    IndexingEvaluationInput,
    IngestionEvaluationThresholds,
    QualityStatus,
    utc_timestamp,
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,512}$")
_PASAL_MARKER_RE = re.compile(r"(?im)^[ \t]*Pasal[ \t]+[0-9]+[A-Z]?[.:]?[ \t]*$")
_STATUS_RANK = {
    QualityStatus.PASS: 0,
    QualityStatus.WARNING: 1,
    QualityStatus.FAIL: 2,
}
_LEGAL_DEPTH = {"bab": 1, "bagian": 2, "paragraf": 3, "pasal": 4, "ayat": 5}


def evaluate_ingestion(
    document: Document,
    sections: Sequence[LegalSection],
    chunks: Sequence[Chunk],
    *,
    embedding: EmbeddingEvaluationInput | None = None,
    indexing: IndexingEvaluationInput | None = None,
    thresholds: IngestionEvaluationThresholds | None = None,
    file_readable: bool = True,
    source_error: str | None = None,
    expected_page_count: int | None = None,
    document_version: int | None = None,
    build_id: str | None = None,
    duration_seconds: float = 0.0,
    generated_at: str | None = None,
    scope: str = "full",
) -> DocumentIngestionEvaluation:
    """Evaluate ingestion artifacts without invoking retrieval or generation."""
    if scope not in {"full", "through_metadata"}:
        raise ValueError("Unknown ingestion evaluation scope")
    config = thresholds or IngestionEvaluationThresholds()
    embedding_input = embedding or EmbeddingEvaluationInput()
    indexing_input = indexing or IndexingEvaluationInput(
        expected_ids=tuple(chunk.chunk_id for chunk in chunks)
    )
    findings: list[EvaluationFinding] = []
    expected_pages = (
        document.page_count if expected_page_count is None else expected_page_count
    )

    document_metrics = _evaluate_document(
        document, expected_pages, file_readable, source_error, config, findings
    )
    page_metrics = _evaluate_pages(document, config, findings)
    structure_metrics = _evaluate_structure(document, sections, findings)
    chunk_metrics = _evaluate_chunks(chunks, config, findings)
    metadata_metrics = _evaluate_metadata(document, chunks, findings)
    embedding_metrics = _evaluate_embeddings(
        chunks, embedding_input, findings if scope == "full" else []
    )
    indexing_metrics = _evaluate_indexing(
        indexing_input, findings if scope == "full" else []
    )
    if scope == "through_metadata":
        embedding_metrics["stage_status"] = "NOT_RUN"
        indexing_metrics["stage_status"] = "NOT_RUN"
    statistics: dict[str, int | float] = {
        "documents_processed": 1,
        "pages_parsed": int(document_metrics["extracted_pages"]),
        "sections_detected": len(sections),
        "chunks_generated": len(chunks),
        "chunks_embedded": int(embedding_metrics["succeeded"]),
        "chunks_indexed": int(indexing_metrics["indexed_chunks"]),
        "failed_embeddings": int(embedding_metrics["failed"]),
        "duration_seconds": round(max(0.0, duration_seconds), 6),
    }

    return DocumentIngestionEvaluation(
        document_id=document.document_id,
        document_version=document_version,
        build_id=build_id,
        ingestion_version=document.ingestion_version,
        status=_overall_status(findings),
        generated_at=generated_at or utc_timestamp(),
        thresholds=asdict(config),
        threshold_rationale=config.rationale(),
        document=document_metrics,
        pages=page_metrics,
        structure=structure_metrics,
        chunks=chunk_metrics,
        metadata=metadata_metrics,
        embedding=embedding_metrics,
        indexing=indexing_metrics,
        statistics=statistics,
        findings=tuple(findings),
        scope=scope,
    )


def _evaluate_document(
    document: Document,
    expected_pages: int,
    file_readable: bool,
    source_error: str | None,
    config: IngestionEvaluationThresholds,
    findings: list[EvaluationFinding],
) -> dict:
    page_records = len(document.pages)
    failed_pages = [
        page.page_number for page in document.pages if _page_extraction_failed(page)
    ]
    successfully_parsed = page_records - len(failed_pages)
    parsing_success_rate = _rate(successfully_parsed, expected_pages)
    expected_numbers = set(range(1, expected_pages + 1))
    actual_numbers = {page.page_number for page in document.pages}
    missing_page_records = sorted(expected_numbers - actual_numbers)
    unexpected_page_records = sorted(actual_numbers - expected_numbers)

    if not file_readable:
        findings.append(
            _finding(
                "document.file_unreadable",
                QualityStatus.FAIL,
                "document",
                "The source file could not be read, so ingestion evidence is incomplete.",
            )
        )
    if source_error:
        findings.append(
            _finding(
                "document.source_processing_error",
                QualityStatus.FAIL,
                "document",
                "Source processing failed before a complete ingestion result was prepared: "
                + source_error,
            )
        )
    if page_records != expected_pages or missing_page_records or unexpected_page_records:
        findings.append(
            _finding(
                "document.page_count_mismatch",
                QualityStatus.FAIL,
                "document",
                "Expected PDF pages and parser page records do not match.",
                metric="page_record_coverage",
                value=page_records,
                threshold=expected_pages,
                affected_items=tuple(
                    [
                        *(f"missing:{value}" for value in missing_page_records),
                        *(f"unexpected:{value}" for value in unexpected_page_records),
                    ]
                ),
            )
        )
    if failed_pages:
        findings.append(
            _finding(
                "document.page_extraction_failures",
                QualityStatus.FAIL,
                "document",
                "One or more source pages failed extraction.",
                metric="extraction_failure_count",
                value=len(failed_pages),
                threshold=0,
                affected_items=_page_items(failed_pages),
            )
        )
    if parsing_success_rate < config.minimum_parsing_success_rate:
        findings.append(
            _finding(
                "document.parsing_success_below_minimum",
                QualityStatus.FAIL,
                "document",
                "The successfully parsed page rate is below the configured minimum.",
                metric="parsing_success_rate",
                value=parsing_success_rate,
                threshold=config.minimum_parsing_success_rate,
            )
        )
    elif parsing_success_rate < 1.0:
        findings.append(
            _finding(
                "document.parsing_incomplete",
                QualityStatus.WARNING,
                "document",
                "The document has page records that were not parsed successfully.",
                metric="parsing_success_rate",
                value=parsing_success_rate,
                threshold=1.0,
            )
        )

    return {
        "file_readable": file_readable,
        "file_path": document.file_path.as_posix() if document.file_path else None,
        "file_hash": document.file_hash,
        "source_error": source_error,
        "expected_pages": expected_pages,
        "page_records": page_records,
        "extracted_pages": successfully_parsed,
        "missing_page_records": missing_page_records,
        "unexpected_page_records": unexpected_page_records,
        "parsing_success_rate": parsing_success_rate,
    }


def _evaluate_pages(
    document: Document,
    config: IngestionEvaluationThresholds,
    findings: list[EvaluationFinding],
) -> dict:
    total = len(document.pages)
    empty = [page.page_number for page in document.pages if not page.cleaned_text.strip()]
    low_density = [
        page.page_number
        for page in document.pages
        if page.cleaned_text.strip()
        and len(page.cleaned_text.strip()) < config.low_text_character_count
    ]
    high_density = [
        page.page_number
        for page in document.pages
        if len(page.cleaned_text) > config.high_text_character_count
    ]
    corruption = {
        page.page_number: _corrupted_character_rate(page.cleaned_text)
        for page in document.pages
    }
    corrupted_warning = sorted(
        page
        for page, rate in corruption.items()
        if rate > config.corrupted_character_warning_rate
    )
    corrupted_failure = sorted(
        page
        for page, rate in corruption.items()
        if rate > config.corrupted_character_fail_rate
    )
    extraction_failures = sorted(
        page.page_number for page in document.pages if _page_extraction_failed(page)
    )
    empty_rate = _rate(len(empty), total)
    low_rate = _rate(len(low_density), total)
    high_rate = _rate(len(high_density), total)

    if empty_rate > config.empty_page_fail_rate:
        findings.append(
            _rate_finding(
                "page.empty_rate_excessive",
                QualityStatus.FAIL,
                "page",
                "The empty-page rate strongly indicates incomplete extraction.",
                "empty_page_rate",
                empty_rate,
                config.empty_page_fail_rate,
                _page_items(empty),
            )
        )
    elif empty_rate > config.empty_page_warning_rate:
        findings.append(
            _rate_finding(
                "page.empty_rate_elevated",
                QualityStatus.WARNING,
                "page",
                "The empty-page rate should be reviewed against the source PDF.",
                "empty_page_rate",
                empty_rate,
                config.empty_page_warning_rate,
                _page_items(empty),
            )
        )
    if low_rate > config.low_text_density_warning_rate:
        findings.append(
            _rate_finding(
                "page.low_text_density",
                QualityStatus.WARNING,
                "page",
                "Many non-empty pages contain less text than the extraction baseline.",
                "low_text_density_rate",
                low_rate,
                config.low_text_density_warning_rate,
                _page_items(low_density),
            )
        )
    if high_rate > config.high_text_density_fail_rate:
        findings.append(
            _rate_finding(
                "page.high_text_density_excessive",
                QualityStatus.FAIL,
                "page",
                "Too many pages contain implausibly dense extracted text.",
                "high_text_density_rate",
                high_rate,
                config.high_text_density_fail_rate,
                _page_items(high_density),
            )
        )
    elif high_density:
        findings.append(
            _finding(
                "page.high_text_density",
                QualityStatus.WARNING,
                "page",
                "At least one page may contain duplicated or malformed layout extraction.",
                metric="high_text_density_page_count",
                value=len(high_density),
                threshold=0,
                affected_items=_page_items(high_density),
            )
        )
    if corrupted_failure:
        findings.append(
            _finding(
                "page.corrupted_characters_excessive",
                QualityStatus.FAIL,
                "page",
                "Replacement or control characters exceed the extraction corruption limit.",
                metric="corrupted_page_count",
                value=len(corrupted_failure),
                threshold=config.corrupted_character_fail_rate,
                affected_items=_page_items(corrupted_failure),
            )
        )
    elif corrupted_warning:
        findings.append(
            _finding(
                "page.corrupted_characters",
                QualityStatus.WARNING,
                "page",
                "Replacement or control characters were detected above the warning limit.",
                metric="corrupted_page_count",
                value=len(corrupted_warning),
                threshold=config.corrupted_character_warning_rate,
                affected_items=_page_items(corrupted_warning),
            )
        )

    densities = [len(page.cleaned_text) for page in document.pages]
    return {
        "count": total,
        "empty_pages": empty,
        "empty_page_rate": empty_rate,
        "low_text_density_pages": low_density,
        "low_text_density_rate": low_rate,
        "high_text_density_pages": high_density,
        "high_text_density_rate": high_rate,
        "corrupted_character_pages": corrupted_warning,
        "corrupted_character_rates": {
            str(page): rate for page, rate in corruption.items() if rate > 0
        },
        "extraction_failure_pages": extraction_failures,
        "text_characters": {
            "min": min(densities, default=0),
            "max": max(densities, default=0),
            "mean": round(statistics.fmean(densities), 3) if densities else 0.0,
        },
    }


def _evaluate_structure(
    document: Document,
    sections: Sequence[LegalSection],
    findings: list[EvaluationFinding],
) -> dict:
    counts = Counter(section.type.casefold() for section in sections)
    node_by_id = {
        section.node_id: section for section in sections if section.node_id is not None
    }
    duplicate_node_ids = _duplicates(
        section.node_id for section in sections if section.node_id is not None
    )
    invalid_hierarchy: set[str] = set()
    orphan_ayat: list[str] = []
    missing_page_references: list[str] = []
    page_numbers = {page.page_number for page in document.pages}

    for section in sections:
        item_id = section.node_id or f"order:{section.order}"
        parent = node_by_id.get(section.parent) if section.parent else None
        section_type = section.type.casefold()
        if section.parent and parent is None:
            invalid_hierarchy.add(item_id)
        if parent is not None:
            parent_depth = _LEGAL_DEPTH.get(parent.type.casefold())
            section_depth = _LEGAL_DEPTH.get(section_type)
            if parent.order >= section.order:
                invalid_hierarchy.add(item_id)
            if (
                parent.page_start > section.page_start
                or parent.page_end < section.page_end
            ):
                invalid_hierarchy.add(item_id)
            if (
                parent_depth is not None
                and section_depth is not None
                and parent_depth >= section_depth
            ):
                invalid_hierarchy.add(item_id)
        if _has_parent_cycle(section, node_by_id):
            invalid_hierarchy.add(item_id)
        if section_type == "document" and section.parent is not None:
            invalid_hierarchy.add(item_id)
        if section_type == "ayat" and (
            parent is None or parent.type.casefold() != "pasal"
        ):
            orphan_ayat.append(item_id)
            invalid_hierarchy.add(item_id)
        if section.page_start not in page_numbers or section.page_end not in page_numbers:
            missing_page_references.append(item_id)
        for child_id in section.children:
            child = node_by_id.get(child_id)
            if child is None or child.parent != section.node_id:
                invalid_hierarchy.add(item_id)

    duplicate_pasal_groups: list[str] = []
    pasal_groups: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for section in sections:
        if section.type.casefold() != "pasal":
            continue
        if section.source_duplicate_of:
            continue
        scope = _legal_scope(section, node_by_id)
        pasal_groups[(scope, section.identifier.casefold())].append(
            section.node_id or f"order:{section.order}"
        )
    for (scope, identifier), node_ids in pasal_groups.items():
        if len(node_ids) > 1:
            duplicate_pasal_groups.append(f"{scope}:{identifier}")

    if orphan_ayat:
        findings.append(
            _finding(
                "structure.orphan_ayat",
                QualityStatus.FAIL,
                "structure",
                "Ayat nodes must have a Pasal parent.",
                metric="orphan_ayat_count",
                value=len(orphan_ayat),
                threshold=0,
                affected_items=tuple(sorted(orphan_ayat)),
            )
        )
    if duplicate_pasal_groups:
        findings.append(
            _finding(
                "structure.duplicate_pasal_identifiers",
                QualityStatus.FAIL,
                "structure",
                "Pasal identifiers are duplicated within the same legal scope.",
                metric="duplicate_pasal_group_count",
                value=len(duplicate_pasal_groups),
                threshold=0,
                affected_items=tuple(sorted(duplicate_pasal_groups)),
            )
        )
    if invalid_hierarchy or duplicate_node_ids:
        affected = sorted(invalid_hierarchy.union(duplicate_node_ids))
        findings.append(
            _finding(
                "structure.invalid_hierarchy",
                QualityStatus.FAIL,
                "structure",
                "The legal tree contains missing, duplicated, or inconsistent relationships.",
                metric="invalid_hierarchy_count",
                value=len(affected),
                threshold=0,
                affected_items=tuple(affected),
            )
        )
    if missing_page_references:
        findings.append(
            _finding(
                "structure.missing_page_references",
                QualityStatus.FAIL,
                "structure",
                "Legal sections reference pages absent from the normalized document.",
                metric="missing_page_reference_count",
                value=len(missing_page_references),
                threshold=0,
                affected_items=tuple(sorted(missing_page_references)),
            )
        )

    return {
        "section_count": len(sections),
        "bab_count": counts["bab"],
        "bagian_count": counts["bagian"],
        "paragraf_count": counts["paragraf"],
        "pasal_count": counts["pasal"],
        "ayat_count": counts["ayat"],
        "orphan_ayat": sorted(orphan_ayat),
        "duplicate_pasal_identifiers": sorted(duplicate_pasal_groups),
        "invalid_hierarchy": sorted(invalid_hierarchy.union(duplicate_node_ids)),
        "missing_page_references": sorted(missing_page_references),
        "source_duplicate_sections": sorted(
            section.node_id or f"order:{section.order}"
            for section in sections
            if section.source_duplicate_of
        ),
    }


def _evaluate_chunks(
    chunks: Sequence[Chunk],
    config: IngestionEvaluationThresholds,
    findings: list[EvaluationFinding],
) -> dict:
    lengths = [chunk.token_count for chunk in chunks]
    short_legal_units = [
        chunk.chunk_id
        for chunk in chunks
        if chunk.token_count < config.minimum_useful_chunk_tokens
    ]
    # A complete Pasal/Ayat is a legally meaningful atomic unit even when it
    # is short. Do not conflate that with an accidental tiny fragment. Keep it
    # visible in the report, but calculate the quality gate only from short
    # unstructured/continuation chunks that actually lose retrieval context.
    too_small = [
        chunk.chunk_id
        for chunk in chunks
        if chunk.chunk_id in short_legal_units
        and not _is_atomic_legal_chunk(chunk)
    ]
    too_large = [
        chunk.chunk_id
        for chunk in chunks
        if chunk.token_count > config.maximum_chunk_tokens
    ]
    content_groups: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for chunk in chunks:
        normalized_content_hash = hashlib.sha256(chunk.content.encode()).hexdigest()
        scope = str(chunk.legal_hierarchy.get("amendment_scope", ""))
        content_groups[(scope, normalized_content_hash)].append(chunk.chunk_id)
    duplicate_groups = {
        content_hash if not scope else f"{scope}:{content_hash}": tuple(ids)
        for (scope, content_hash), ids in content_groups.items()
        if len(ids) > 1
    }
    duplicate_count = sum(len(ids) - 1 for ids in duplicate_groups.values())
    too_small_rate = _rate(len(too_small), len(chunks))
    too_large_rate = _rate(len(too_large), len(chunks))
    duplicate_rate = _rate(duplicate_count, len(chunks))

    if not chunks:
        findings.append(
            _finding(
                "chunks.none_generated",
                QualityStatus.FAIL,
                "chunks",
                "No chunks were generated for the document.",
                metric="chunk_count",
                value=0,
                threshold=1,
            )
        )
    if too_large:
        findings.append(
            _finding(
                "chunks.maximum_tokens_exceeded",
                QualityStatus.FAIL,
                "chunks",
                "One or more chunks exceed the configured embedding token ceiling.",
                metric="too_large_chunk_rate",
                value=too_large_rate,
                threshold=0,
                affected_items=tuple(too_large),
            )
        )
    if too_small_rate > config.too_small_chunk_fail_rate:
        findings.append(
            _rate_finding(
                "chunks.too_small_rate_excessive",
                QualityStatus.FAIL,
                "chunks",
                "Most chunks are below the minimum useful token target.",
                "too_small_chunk_rate",
                too_small_rate,
                config.too_small_chunk_fail_rate,
                tuple(too_small),
            )
        )
    elif too_small_rate > config.too_small_chunk_warning_rate:
        findings.append(
            _rate_finding(
                "chunks.too_small_rate_elevated",
                QualityStatus.WARNING,
                "chunks",
                "Many chunks are below the useful token target; short provisions may be valid.",
                "too_small_chunk_rate",
                too_small_rate,
                config.too_small_chunk_warning_rate,
                tuple(too_small),
            )
        )
    if duplicate_rate > config.duplicate_chunk_fail_rate:
        findings.append(
            _rate_finding(
                "chunks.duplicate_rate_excessive",
                QualityStatus.FAIL,
                "chunks",
                "Exact duplicate chunk content exceeds the configured limit.",
                "duplicate_chunk_rate",
                duplicate_rate,
                config.duplicate_chunk_fail_rate,
                tuple(sorted(duplicate_groups)),
            )
        )
    elif duplicate_rate > config.duplicate_chunk_warning_rate:
        findings.append(
            _rate_finding(
                "chunks.duplicates_detected",
                QualityStatus.WARNING,
                "chunks",
                "Exact duplicate chunk content was detected.",
                "duplicate_chunk_rate",
                duplicate_rate,
                config.duplicate_chunk_warning_rate,
                tuple(sorted(duplicate_groups)),
            )
        )

    return {
        "count": len(chunks),
        "token_length_distribution": {
            "min": min(lengths, default=0),
            "max": max(lengths, default=0),
            "mean": round(statistics.fmean(lengths), 3) if lengths else 0.0,
            "median": round(float(statistics.median(lengths)), 3) if lengths else 0.0,
            "p95": _percentile(lengths, 0.95),
            "p99": _percentile(lengths, 0.99),
        },
        "too_small_chunk_ids": too_small,
        "too_small_chunk_rate": too_small_rate,
        "short_atomic_legal_chunk_ids": [
            chunk_id
            for chunk_id in short_legal_units
            if chunk_id not in too_small
        ],
        "short_atomic_legal_chunk_rate": _rate(
            len(short_legal_units) - len(too_small), len(chunks)
        ),
        "too_large_chunk_ids": too_large,
        "too_large_chunk_rate": too_large_rate,
        "duplicate_chunk_groups": duplicate_groups,
        "duplicate_chunk_rate": duplicate_rate,
    }


def _is_atomic_legal_chunk(chunk: Chunk) -> bool:
    return bool(chunk.legal_hierarchy.get("pasal")) and not chunk.chunk_type.endswith(
        "continuation"
    )


def _evaluate_metadata(
    document: Document,
    chunks: Sequence[Chunk],
    findings: list[EvaluationFinding],
) -> dict:
    document_page_numbers = {page.page_number for page in document.pages}
    missing_document_id = not bool(document.document_id.strip())
    invalid_document_id = bool(document.document_id) and not _SAFE_ID_RE.fullmatch(
        document.document_id
    )
    missing_source = not bool(document.source.strip())
    invalid_file_hash = not re.fullmatch(r"[a-fA-F0-9]{64}", document.file_hash)
    missing_document_ids = [
        chunk.chunk_id or "<missing>"
        for chunk in chunks
        if not chunk.document_id or chunk.document_id != document.document_id
    ]
    missing_sources = [
        chunk.chunk_id or "<missing>"
        for chunk in chunks
        if not (chunk.source or str(chunk.metadata.get("source", ""))).strip()
    ]
    missing_pages = [
        chunk.chunk_id or "<missing>"
        for chunk in chunks
        if any(
            page_number not in document_page_numbers
            for page_number in range(chunk.page_start, chunk.page_end + 1)
        )
    ]
    missing_pasal = [
        chunk.chunk_id or "<missing>"
        for chunk in chunks
        if _PASAL_MARKER_RE.search(chunk.content)
        and not str(chunk.legal_hierarchy.get("pasal", "")).strip()
    ]
    invalid_hierarchy = [
        chunk.chunk_id or "<missing>"
        for chunk in chunks
        if chunk.legal_hierarchy.get("ayat")
        and not chunk.legal_hierarchy.get("pasal")
    ]
    invalid_ids = [
        chunk.chunk_id or "<missing>"
        for chunk in chunks
        if not _SAFE_ID_RE.fullmatch(chunk.chunk_id)
    ]
    duplicate_ids = _duplicates(chunk.chunk_id for chunk in chunks)
    invalid_content_hashes = [
        chunk.chunk_id or "<missing>"
        for chunk in chunks
        if chunk.content_hash != hashlib.sha256(chunk.content.encode()).hexdigest()
    ]
    affected_chunks = set(
        missing_document_ids
        + missing_sources
        + missing_pages
        + missing_pasal
        + invalid_hierarchy
        + invalid_ids
        + duplicate_ids
        + invalid_content_hashes
    )
    missing_required_rate = _rate(len(affected_chunks), len(chunks))

    if missing_document_id or invalid_document_id or missing_source or invalid_file_hash:
        findings.append(
            _finding(
                "metadata.document_provenance_missing",
                QualityStatus.FAIL,
                "metadata",
                "Required document identity or source provenance is missing.",
                affected_items=tuple(
                    name
                    for name, missing in (
                        ("document_id", missing_document_id),
                        ("invalid_document_id", invalid_document_id),
                        ("source", missing_source),
                        ("file_hash", invalid_file_hash),
                    )
                    if missing
                ),
            )
        )
    if affected_chunks:
        findings.append(
            _finding(
                "metadata.chunk_provenance_invalid",
                QualityStatus.FAIL,
                "metadata",
                "One or more chunks have missing or inconsistent required provenance.",
                metric="missing_required_metadata_rate",
                value=missing_required_rate,
                threshold=0,
                affected_items=tuple(sorted(affected_chunks)),
            )
        )

    return {
        "missing_document_id": missing_document_id,
        "invalid_document_id": invalid_document_id,
        "missing_source": missing_source,
        "invalid_file_hash": invalid_file_hash,
        "missing_document_id_chunk_ids": missing_document_ids,
        "missing_source_chunk_ids": missing_sources,
        "missing_page_chunk_ids": missing_pages,
        "missing_pasal_chunk_ids": missing_pasal,
        "invalid_hierarchy_chunk_ids": invalid_hierarchy,
        "invalid_chunk_ids": sorted(set(invalid_ids).union(duplicate_ids)),
        "invalid_content_hash_chunk_ids": invalid_content_hashes,
        "missing_required_metadata_rate": missing_required_rate,
    }


def _evaluate_embeddings(
    chunks: Sequence[Chunk],
    embedding: EmbeddingEvaluationInput,
    findings: list[EvaluationFinding],
) -> dict:
    attempted = set(embedding.attempted_ids)
    succeeded = set(embedding.succeeded_ids)
    failed = set(embedding.failed_ids).union(attempted - succeeded)
    dimension_mismatch = set(embedding.dimension_mismatch_ids)
    expected = {chunk.chunk_id for chunk in chunks}
    success_rate = _rate(len(succeeded), len(attempted))

    if embedding.evaluated:
        missing_attempts = sorted(expected - attempted)
        unexpected_attempts = sorted(attempted - expected)
        if missing_attempts or unexpected_attempts:
            findings.append(
                _finding(
                    "embedding.attempted_chunk_mismatch",
                    QualityStatus.FAIL,
                    "embedding",
                    "Embedding attempts do not match the finalized chunk set.",
                    affected_items=tuple(missing_attempts + unexpected_attempts),
                )
            )
        if failed:
            findings.append(
                _finding(
                    "embedding.failures",
                    QualityStatus.FAIL,
                    "embedding",
                    "One or more finalized chunks failed embedding generation.",
                    metric="embedding_success_rate",
                    value=success_rate,
                    threshold=1.0,
                    affected_items=tuple(sorted(failed)),
                )
            )
        if dimension_mismatch:
            findings.append(
                _finding(
                    "embedding.dimension_mismatch",
                    QualityStatus.FAIL,
                    "embedding",
                    "Embedding dimensions do not match the configured vector space.",
                    metric="dimension_mismatch_count",
                    value=len(dimension_mismatch),
                    threshold=0,
                    affected_items=tuple(sorted(dimension_mismatch)),
                )
            )
        if not embedding.model or not embedding.revision or not embedding.expected_dimension:
            findings.append(
                _finding(
                    "embedding.provenance_missing",
                    QualityStatus.FAIL,
                    "embedding",
                    "Embedding model, revision, and expected dimension must be recorded.",
                )
            )
    elif chunks:
        findings.append(
            _finding(
                "embedding.not_evaluated",
                QualityStatus.WARNING,
                "embedding",
                "Embedding generation has not been evaluated for finalized chunks.",
            )
        )

    return {
        "evaluated": embedding.evaluated,
        "attempted": len(attempted),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "failed_chunk_ids": sorted(failed),
        "success_rate": success_rate if embedding.evaluated else None,
        "dimension_mismatch": len(dimension_mismatch),
        "dimension_mismatch_chunk_ids": sorted(dimension_mismatch),
        "model": embedding.model,
        "revision": embedding.revision,
        "expected_dimension": embedding.expected_dimension,
        "error": embedding.error,
    }


def _evaluate_indexing(
    indexing: IndexingEvaluationInput,
    findings: list[EvaluationFinding],
) -> dict:
    expected = set(indexing.expected_ids)
    indexed = set(indexing.indexed_ids)
    missing = sorted(expected - indexed)
    unexpected = sorted(indexed - expected)
    consistency = (
        _rate(len(expected.intersection(indexed)), len(expected))
        if expected
        else float(not indexed)
    )
    if indexing.evaluated and (missing or unexpected or len(indexed) != len(expected)):
        findings.append(
            _finding(
                "indexing.vector_mismatch",
                QualityStatus.FAIL,
                "indexing",
                "Indexed vector IDs do not exactly match the expected chunk IDs.",
                metric="index_consistency",
                value=consistency,
                threshold=1.0,
                affected_items=tuple(
                    [
                        *(f"missing:{item}" for item in missing),
                        *(f"unexpected:{item}" for item in unexpected),
                    ]
                ),
            )
        )
    elif not indexing.evaluated and expected:
        findings.append(
            _finding(
                "indexing.not_evaluated",
                QualityStatus.WARNING,
                "indexing",
                "Vector indexing has not yet been reconciled with finalized chunks.",
                metric="expected_chunks",
                value=len(expected),
            )
        )
    return {
        "evaluated": indexing.evaluated,
        "expected_chunks": len(expected),
        "indexed_chunks": len(indexed),
        "missing_vectors": missing,
        "unexpected_vectors": unexpected,
        "index_consistency": consistency if indexing.evaluated else None,
        "namespace": indexing.namespace,
        "release_id": indexing.release_id,
    }


def _legal_scope(
    section: LegalSection,
    node_by_id: dict[str, LegalSection],
) -> str:
    if section.amendment_scope:
        if section.amendment_scope == section.node_id:
            # The enacting Pasal and a quoted Pasal can legitimately carry
            # the same number. The former names the amendment block; the
            # latter belongs inside it, so they are distinct legal scopes.
            return f"enacting:{section.node_id}"
        return section.amendment_scope
    if section.parent:
        # The immediate structural container is the minimum deterministic
        # scope when no amendment owner exists. Two Pasal labels in different
        # BAB/Bagian/Paragraf are not competing identities.
        return f"parent:{section.parent}"
    current = section
    visited: set[str] = set()
    while current.parent and current.parent not in visited:
        visited.add(current.parent)
        parent = node_by_id.get(current.parent)
        if parent is None:
            break
        if parent.type.casefold() in {"penjelasan", "lampiran"}:
            return parent.node_id or parent.identifier.casefold()
        current = parent
    return "document"


def _has_parent_cycle(
    section: LegalSection,
    node_by_id: dict[str, LegalSection],
) -> bool:
    visited = {section.node_id} if section.node_id else set()
    current = section
    while current.parent:
        if current.parent in visited:
            return True
        visited.add(current.parent)
        parent = node_by_id.get(current.parent)
        if parent is None:
            return False
        current = parent
    return False


def _corrupted_character_rate(text: str) -> float:
    if not text:
        return 0.0
    corrupted = sum(
        character == "\ufffd"
        or (
            unicodedata.category(character).startswith("C")
            and character not in {"\n", "\r", "\t"}
        )
        for character in text
    )
    return round(corrupted / len(text), 6)


def _page_extraction_failed(page: Page) -> bool:
    return bool(page.metadata.get("extraction_failed")) or any(
        diagnostic.code == "pdf.page_extraction_failed"
        or diagnostic.severity == "error"
        for diagnostic in page.diagnostics
    )


def _percentile(values: Sequence[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return float(ordered[index])


def _duplicates(values: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _page_items(pages: Sequence[int]) -> tuple[str, ...]:
    return tuple(f"page:{page}" for page in pages)


def _finding(
    code: str,
    status: QualityStatus,
    category: str,
    message: str,
    *,
    metric: str | None = None,
    value: int | float | str | None = None,
    threshold: int | float | str | None = None,
    affected_items: tuple[str, ...] = (),
) -> EvaluationFinding:
    return EvaluationFinding(
        code=code,
        status=status,
        category=category,
        message=message,
        metric=metric,
        value=value,
        threshold=threshold,
        affected_items=affected_items,
    )


def _rate_finding(
    code: str,
    status: QualityStatus,
    category: str,
    message: str,
    metric: str,
    value: float,
    threshold: float,
    affected_items: tuple[str, ...],
) -> EvaluationFinding:
    return _finding(
        code,
        status,
        category,
        message,
        metric=metric,
        value=value,
        threshold=threshold,
        affected_items=affected_items,
    )


def _overall_status(findings: Sequence[EvaluationFinding]) -> QualityStatus:
    return max(
        (finding.status for finding in findings),
        key=lambda status: _STATUS_RANK[status],
        default=QualityStatus.PASS,
    )
