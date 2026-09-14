from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from app.services.ingestion.builds import IngestionBuildConfig
from app.services.ingestion.domain import (
    Chunk,
    Document,
    ExtractionDiagnostic,
    LegalSection,
    Page,
)
from app.services.ingestion.evaluation import (
    EmbeddingEvaluationInput,
    IndexingEvaluationInput,
    IngestionEvaluationThresholds,
    QualityStatus,
    aggregate_ingestion_reports,
    evaluate_ingestion,
    finalize_indexing_report,
    write_corpus_report,
    write_document_report,
)


def _page(number: int, text: str | None = None) -> Page:
    content = text or (
        f"Pasal {number}\nSetiap pekerja berhak memperoleh perlindungan dan "
        "pengusaha wajib melaksanakan ketentuan peraturan perundang-undangan."
    )
    return Page(page_number=number, raw_text=content, cleaned_text=content)


def _document(
    pages: tuple[Page, ...] | None = None,
    *,
    document_id: str = "PP-35-2021",
    source: str = "JDIH BPK",
) -> Document:
    resolved_pages = pages or (_page(1),)
    return Document(
        document_id=document_id,
        title="Peraturan Pemerintah Nomor 35 Tahun 2021",
        source=source,
        source_url="https://peraturan.bpk.go.id/Details/161904",
        file_path=Path("dataset/PP Nomor 35 Tahun 2021.pdf"),
        file_hash="a" * 64,
        page_count=len(resolved_pages),
        metadata={"regulation_type": "PP", "number": 35, "year": 2021},
        ingestion_version="kerjapedia-ingestion-v5-evaluated",
        pages=resolved_pages,
    )


def _sections(page_end: int = 1) -> tuple[LegalSection, ...]:
    return (
        LegalSection(
            type="document",
            identifier="PP-35-2021",
            title="PP 35/2021",
            text="Pasal 15\n(1) Ketentuan berlaku.",
            page_start=1,
            page_end=page_end,
            children=("node-pasal",),
            order=0,
            node_id="node-root",
        ),
        LegalSection(
            type="pasal",
            identifier="Pasal 15",
            title=None,
            text="Pasal 15\n(1) Ketentuan berlaku.",
            page_start=1,
            page_end=page_end,
            parent="node-root",
            children=("node-ayat",),
            order=1,
            node_id="node-pasal",
        ),
        LegalSection(
            type="ayat",
            identifier="Ayat (1)",
            title=None,
            text="(1) Ketentuan berlaku.",
            page_start=1,
            page_end=page_end,
            parent="node-pasal",
            order=2,
            node_id="node-ayat",
        ),
    )


def _chunk(
    chunk_id: str = "PP-35-2021:chunk:001",
    *,
    content: str = "Pasal 15\n(1) Ketentuan perlindungan pekerja berlaku.",
    token_count: int = 100,
    page_start: int = 1,
    source: str | None = "JDIH BPK",
    hierarchy: dict[str, str] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="PP-35-2021",
        content=content,
        page_start=page_start,
        page_end=page_start,
        legal_hierarchy=hierarchy or {"pasal": "15", "ayat": "1"},
        metadata={"source": source or ""},
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        source=source,
        source_url="https://peraturan.bpk.go.id/Details/161904",
        token_count=token_count,
    )


def _embedding(*chunk_ids: str) -> EmbeddingEvaluationInput:
    return EmbeddingEvaluationInput(
        attempted_ids=chunk_ids,
        succeeded_ids=chunk_ids,
        model="BAAI/bge-m3",
        revision="pinned-revision",
        expected_dimension=1024,
        evaluated=True,
    )


def _indexing(*chunk_ids: str) -> IndexingEvaluationInput:
    return IndexingEvaluationInput(
        expected_ids=chunk_ids,
        indexed_ids=chunk_ids,
        evaluated=True,
        namespace="release-test",
    )


def test_clean_document_evaluation_passes_with_complete_metrics() -> None:
    chunk = _chunk()
    report = evaluate_ingestion(
        _document(),
        _sections(),
        [chunk],
        embedding=_embedding(chunk.chunk_id),
        indexing=_indexing(chunk.chunk_id),
        document_version=1,
        build_id="ingb-clean",
        generated_at="2026-09-13T00:00:00+00:00",
    )

    assert report.status == QualityStatus.PASS
    assert report.document["file_readable"] is True
    assert report.document["parsing_success_rate"] == 1.0
    assert report.structure["pasal_count"] == 1
    assert report.structure["ayat_count"] == 1
    assert report.chunks["token_length_distribution"] == {
        "min": 100,
        "max": 100,
        "mean": 100.0,
        "median": 100.0,
        "p95": 100.0,
        "p99": 100.0,
    }
    assert report.embedding["succeeded"] == 1
    assert report.indexing["index_consistency"] == 1.0
    assert report.statistics["documents_processed"] == 1
    assert report.statistics["chunks_indexed"] == 1
    assert report.findings == ()


def test_page_failures_and_density_problems_explain_document_failure() -> None:
    failed = Page(
        page_number=2,
        raw_text="",
        cleaned_text="",
        diagnostics=(
            ExtractionDiagnostic(
                code="pdf.page_extraction_failed",
                message="Page failed.",
                severity="error",
                page_number=2,
            ),
        ),
        metadata={"extraction_failed": True},
    )
    corrupted = _page(3, "�" * 100)
    dense = _page(4, "ketentuan " * 2_501)
    document = _document((_page(1), failed, corrupted, dense))

    report = evaluate_ingestion(
        document,
        _sections(page_end=4),
        [_chunk()],
        embedding=_embedding("PP-35-2021:chunk:001"),
        build_id="ingb-pages",
    )
    codes = {finding.code for finding in report.findings}

    assert report.status == QualityStatus.FAIL
    assert report.pages["empty_page_rate"] == 0.25
    assert report.pages["high_text_density_pages"] == [4]
    assert report.pages["corrupted_character_pages"] == [3]
    assert report.pages["extraction_failure_pages"] == [2]
    assert "document.page_extraction_failures" in codes
    assert "page.empty_rate_excessive" in codes
    assert "page.corrupted_characters_excessive" in codes
    assert "page.high_text_density_excessive" in codes


def test_structure_evaluation_detects_orphans_duplicates_and_missing_pages() -> None:
    root, pasal, _ = _sections()
    duplicate = replace(pasal, node_id="node-pasal-duplicate", order=3)
    orphan = LegalSection(
        type="ayat",
        identifier="Ayat (2)",
        title=None,
        text="(2) Isi.",
        page_start=2,
        page_end=2,
        parent=root.node_id,
        order=4,
        node_id="node-orphan",
    )
    reversed_hierarchy = LegalSection(
        type="bagian",
        identifier="Bagian Kesatu",
        title=None,
        text="Bagian Kesatu",
        page_start=1,
        page_end=1,
        parent=pasal.node_id,
        order=5,
        node_id="node-reversed",
    )

    report = evaluate_ingestion(
        _document(),
        [root, pasal, duplicate, orphan, reversed_hierarchy],
        [_chunk()],
        embedding=_embedding("PP-35-2021:chunk:001"),
        build_id="ingb-structure",
    )
    codes = {finding.code for finding in report.findings}

    assert report.structure["duplicate_pasal_identifiers"]
    assert report.structure["orphan_ayat"] == ["node-orphan"]
    assert "node-reversed" in report.structure["invalid_hierarchy"]
    assert report.structure["missing_page_references"] == ["node-orphan"]
    assert "structure.duplicate_pasal_identifiers" in codes
    assert "structure.invalid_hierarchy" in codes
    assert "structure.missing_page_references" in codes


def test_chunk_distribution_duplicate_rates_and_thresholds_are_configurable() -> None:
    chunks = [
        _chunk("chunk-1", content="Pasal 15\nIsi sama.", token_count=10),
        _chunk("chunk-2", content="Pasal 15\nIsi sama.", token_count=20),
    ]
    default = evaluate_ingestion(
        _document(),
        _sections(),
        chunks,
        embedding=_embedding("chunk-1", "chunk-2"),
        indexing=_indexing("chunk-1", "chunk-2"),
        build_id="ingb-default",
    )
    permissive = evaluate_ingestion(
        _document(),
        _sections(),
        chunks,
        embedding=_embedding("chunk-1", "chunk-2"),
        indexing=_indexing("chunk-1", "chunk-2"),
        thresholds=IngestionEvaluationThresholds(
            minimum_useful_chunk_tokens=1,
            duplicate_chunk_warning_rate=1.0,
            duplicate_chunk_fail_rate=1.0,
        ),
        build_id="ingb-permissive",
    )

    assert default.chunks["duplicate_chunk_rate"] == 0.5
    assert default.chunks["token_length_distribution"]["median"] == 15.0
    assert default.status == QualityStatus.FAIL
    assert permissive.status == QualityStatus.PASS
    assert permissive.threshold_rationale["duplicates"]

    base_config = IngestionBuildConfig(runtime={})
    changed_config = replace(
        base_config,
        evaluation_thresholds={"duplicate_chunk_fail_rate": 0.01},
    )
    assert base_config.config_hash != changed_config.config_hash


def test_short_complete_legal_units_are_reported_but_not_treated_as_fragments() -> None:
    chunk = _chunk(token_count=10)

    report = evaluate_ingestion(
        _document(),
        _sections(),
        [chunk],
        embedding=_embedding(chunk.chunk_id),
        indexing=_indexing(chunk.chunk_id),
        build_id="ingb-short-legal-unit",
    )

    assert report.status == QualityStatus.PASS
    assert report.chunks["too_small_chunk_ids"] == []
    assert report.chunks["short_atomic_legal_chunk_ids"] == [chunk.chunk_id]


def test_metadata_scope_does_not_require_embedding_or_hide_structure_failure() -> None:
    report = evaluate_ingestion(_document(), _sections(), [_chunk()], scope="through_metadata")
    assert report.status == QualityStatus.PASS
    assert report.scope == "through_metadata"
    assert report.embedding["stage_status"] == "NOT_RUN"
    assert report.embedding["evaluated"] is False
    bad_ayat = replace(_sections()[2], parent="node-root")
    failed = evaluate_ingestion(
        _document(),
        [*_sections()[:2], bad_ayat],
        [_chunk()],
        scope="through_metadata",
    )
    assert failed.status == QualityStatus.FAIL
    assert any(f.code == "structure.orphan_ayat" for f in failed.findings)


def test_metadata_embedding_and_indexing_failures_name_affected_chunks() -> None:
    invalid = replace(
        _chunk("chunk invalid", page_start=2, source=None, hierarchy={"ayat": "1"}),
        content_hash="0" * 64,
    )
    report = evaluate_ingestion(
        _document(),
        _sections(),
        [invalid],
        embedding=EmbeddingEvaluationInput(
            attempted_ids=(invalid.chunk_id,),
            succeeded_ids=(),
            failed_ids=(invalid.chunk_id,),
            dimension_mismatch_ids=(invalid.chunk_id,),
            model="BAAI/bge-m3",
            revision="pinned-revision",
            expected_dimension=1024,
            evaluated=True,
        ),
        indexing=IndexingEvaluationInput(
            expected_ids=(invalid.chunk_id,),
            indexed_ids=(),
            evaluated=True,
            namespace="release-test",
        ),
        build_id="ingb-invalid",
    )
    codes = {finding.code for finding in report.findings}

    assert report.metadata["missing_page_chunk_ids"] == [invalid.chunk_id]
    assert report.metadata["missing_source_chunk_ids"] == [invalid.chunk_id]
    assert report.metadata["invalid_chunk_ids"] == [invalid.chunk_id]
    assert report.embedding["failed_chunk_ids"] == [invalid.chunk_id]
    assert report.indexing["missing_vectors"] == [invalid.chunk_id]
    assert "metadata.chunk_provenance_invalid" in codes
    assert "embedding.failures" in codes
    assert "embedding.dimension_mismatch" in codes
    assert "indexing.vector_mismatch" in codes


def test_reports_are_machine_readable_human_readable_and_aggregated(
    tmp_path: Path,
) -> None:
    root = tmp_path / "reports" / "ingestion"
    clean_chunk = _chunk()
    passed = evaluate_ingestion(
        _document(),
        _sections(),
        [clean_chunk],
        embedding=_embedding(clean_chunk.chunk_id),
        indexing=_indexing(clean_chunk.chunk_id),
        document_version=1,
        build_id="ingb-pass",
        generated_at="2026-09-13T00:00:00+00:00",
    )
    failed = evaluate_ingestion(
        _document(document_id="UU-13-2003"),
        (),
        (),
        file_readable=False,
        document_version=2,
        build_id="ingb-fail",
        generated_at="2026-09-13T00:00:00+00:00",
    )

    paths = write_document_report(passed, root)
    write_document_report(failed, root)
    aggregate_paths = write_corpus_report(root)

    payload = json.loads(Path(paths["latest_json"]).read_text(encoding="utf-8"))
    aggregate = json.loads(Path(aggregate_paths["json"]).read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert (
        Path(paths["immutable_markdown"])
        .read_text(encoding="utf-8")
        .startswith("# Ingestion Evaluation")
    )
    assert aggregate["document_count"] == 2
    assert aggregate["status"] == "FAIL"
    assert aggregate["status_counts"] == {"PASS": 1, "WARNING": 0, "FAIL": 1}
    assert aggregate["failure_reasons"]["document.file_unreadable"] == 1

    direct = aggregate_ingestion_reports([payload], generated_at="fixed")
    assert direct.status == QualityStatus.PASS
    assert direct.generated_at == "fixed"


def test_release_indexing_report_preserves_build_report_and_updates_latest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "reports" / "ingestion"
    chunk = _chunk()
    report = evaluate_ingestion(
        _document(),
        _sections(),
        [chunk],
        embedding=_embedding(chunk.chunk_id),
        build_id="ingb-indexed",
    )
    paths = write_document_report(report, root)
    immutable_before = Path(paths["immutable_json"]).read_bytes()

    assert report.status == QualityStatus.WARNING
    assert report.indexing["expected_chunks"] == 1

    indexed_paths = finalize_indexing_report(
        root,
        document_id=report.document_id,
        build_id="ingb-indexed",
        expected_ids=[chunk.chunk_id],
        indexed_ids=[chunk.chunk_id],
        namespace="release-namespace",
        release_id="release-1",
    )

    assert indexed_paths is not None
    latest = json.loads(Path(indexed_paths["latest_json"]).read_text(encoding="utf-8"))
    assert latest["indexing"]["index_consistency"] == 1.0
    assert latest["indexing"]["missing_vectors"] == []
    assert latest["status"] == "PASS"
    assert Path(paths["immutable_json"]).read_bytes() == immutable_before

    failed_build = replace(report, build_id="ingb-index-failed")
    write_document_report(failed_build, root)
    failed_paths = finalize_indexing_report(
        root,
        document_id=report.document_id,
        build_id="ingb-index-failed",
        expected_ids=[chunk.chunk_id],
        indexed_ids=[],
        namespace="failed-release-namespace",
        release_id="release-failed",
    )
    assert failed_paths is not None
    failed_payload = json.loads(Path(failed_paths["release_json"]).read_text(encoding="utf-8"))
    assert failed_payload["status"] == "FAIL"
    assert failed_payload["indexing"]["missing_vectors"] == [chunk.chunk_id]
