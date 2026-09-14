from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.evaluation.models import (
    CorpusIngestionEvaluation,
    DocumentIngestionEvaluation,
    QualityStatus,
    utc_timestamp,
)

_STATUS_RANK = {"PASS": 0, "WARNING": 1, "FAIL": 2}


def write_document_report(
    report: DocumentIngestionEvaluation,
    reports_root: Path,
) -> dict[str, str]:
    """Write an immutable build report and a convenient latest-document view."""
    if not report.build_id:
        raise ValueError("build_id is required when writing an ingestion report")
    store = ArtifactStore(reports_root)
    payload = report.to_dict()
    immutable_base = Path("builds") / report.document_id / report.build_id
    immutable_json = store.write_json(immutable_base.with_suffix(".json"), payload)
    immutable_markdown = store.write_bytes(
        immutable_base.with_suffix(".md"),
        render_document_markdown(payload).encode(),
    )
    latest_json = store.write_json(Path(f"{report.document_id}.json"), payload)
    latest_markdown = store.write_bytes(
        Path(f"{report.document_id}.md"),
        render_document_markdown(payload).encode(),
    )
    return {
        "immutable_json": immutable_json,
        "immutable_markdown": immutable_markdown,
        "latest_json": latest_json,
        "latest_markdown": latest_markdown,
    }


def finalize_indexing_report(
    reports_root: Path,
    *,
    document_id: str,
    build_id: str,
    expected_ids: Sequence[str],
    indexed_ids: Sequence[str],
    namespace: str,
    release_id: str,
) -> dict[str, str] | None:
    """Create a release-scoped report without mutating the immutable build report."""
    source = reports_root / "builds" / document_id / f"{build_id}.json"
    if not source.is_file():
        return None
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("document_id") != document_id or payload.get("build_id") != build_id:
        raise RuntimeError("Ingestion evaluation report identity mismatch")

    expected = set(expected_ids)
    indexed = set(indexed_ids)
    missing = sorted(expected - indexed)
    unexpected = sorted(indexed - expected)
    consistency = (
        round(len(expected.intersection(indexed)) / len(expected), 6)
        if expected
        else float(not indexed)
    )
    findings = [
        finding
        for finding in payload.get("findings", [])
        if not str(finding.get("code", "")).startswith("indexing.")
    ]
    if missing or unexpected or len(expected) != len(indexed):
        findings.append(
            {
                "code": "indexing.vector_mismatch",
                "status": "FAIL",
                "category": "indexing",
                "message": "Indexed vector IDs do not exactly match expected chunks.",
                "metric": "index_consistency",
                "value": consistency,
                "threshold": 1.0,
                "affected_items": [
                    *(f"missing:{item}" for item in missing),
                    *(f"unexpected:{item}" for item in unexpected),
                ],
            }
        )
    payload["generated_at"] = utc_timestamp()
    payload["indexing"] = {
        "evaluated": True,
        "expected_chunks": len(expected),
        "indexed_chunks": len(indexed),
        "missing_vectors": missing,
        "unexpected_vectors": unexpected,
        "index_consistency": consistency,
        "namespace": namespace,
        "release_id": release_id,
    }
    payload.setdefault("statistics", {})["chunks_indexed"] = len(indexed)
    payload["findings"] = findings
    payload["status"] = _payload_status(findings)

    store = ArtifactStore(reports_root)
    release_base = Path("releases") / release_id / document_id
    release_json = store.write_json(release_base.with_suffix(".json"), payload)
    release_markdown = store.write_bytes(
        release_base.with_suffix(".md"),
        render_document_markdown(payload).encode(),
    )
    latest_json = store.write_json(Path(f"{document_id}.json"), payload)
    latest_markdown = store.write_bytes(
        Path(f"{document_id}.md"),
        render_document_markdown(payload).encode(),
    )
    return {
        "release_json": release_json,
        "release_markdown": release_markdown,
        "latest_json": latest_json,
        "latest_markdown": latest_markdown,
    }


def aggregate_ingestion_reports(
    reports: Sequence[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> CorpusIngestionEvaluation:
    valid = [
        report for report in reports if report.get("schema_version") == "ingestion-evaluation-v1"
    ]
    status_counts = Counter(str(report.get("status", "FAIL")) for report in valid)
    scopes = {report.get("scope", "full") for report in valid}
    scope = next(iter(scopes)) if len(scopes) == 1 else "mixed"
    failure_reasons = Counter(
        str(finding.get("code"))
        for report in valid
        for finding in report.get("findings", [])
        if finding.get("status") == "FAIL"
    )
    totals: dict[str, int | float | str | None] = {
        "expected_pages": sum(_metric(report, "document", "expected_pages") for report in valid),
        "extracted_pages": sum(_metric(report, "document", "extracted_pages") for report in valid),
        "empty_pages": sum(
            len((report.get("pages") or {}).get("empty_pages", [])) for report in valid
        ),
        "extraction_failures": sum(
            len((report.get("pages") or {}).get("extraction_failure_pages", [])) for report in valid
        ),
        "sections_detected": sum(_metric(report, "structure", "section_count") for report in valid),
        "pasal_detected": sum(_metric(report, "structure", "pasal_count") for report in valid),
        "chunks_generated": sum(_metric(report, "chunks", "count") for report in valid),
        "embeddings_attempted": sum(_metric(report, "embedding", "attempted") for report in valid),
        "embeddings_succeeded": sum(_metric(report, "embedding", "succeeded") for report in valid),
        "embeddings_failed": sum(_metric(report, "embedding", "failed") for report in valid),
        "vectors_expected": sum(_metric(report, "indexing", "expected_chunks") for report in valid),
        "vectors_indexed": sum(_metric(report, "indexing", "indexed_chunks") for report in valid),
        "missing_vectors": sum(
            len((report.get("indexing") or {}).get("missing_vectors", [])) for report in valid
        ),
        "duration_seconds": round(
            sum(
                float((report.get("statistics") or {}).get("duration_seconds", 0) or 0)
                for report in valid
            ),
            6,
        ),
    }
    expected_pages = int(totals["expected_pages"])
    attempted_embeddings = int(totals["embeddings_attempted"])
    expected_vectors = int(totals["vectors_expected"])
    totals["parsing_success_rate"] = _ratio(int(totals["extracted_pages"]), expected_pages)
    totals["embedding_success_rate"] = _ratio(
        int(totals["embeddings_succeeded"]), attempted_embeddings
    )
    matched_vectors = sum(
        max(
            0,
            _metric(report, "indexing", "expected_chunks")
            - len((report.get("indexing") or {}).get("missing_vectors", [])),
        )
        for report in valid
        if (report.get("indexing") or {}).get("evaluated")
    )
    totals["index_consistency"] = (
        _ratio(matched_vectors, expected_vectors) if expected_vectors else 1.0
    )
    if scope == "through_metadata":
        totals.update(
            embedding_status="NOT_RUN",
            indexing_status="NOT_RUN",
            embedding_success_rate=None,
            index_consistency=None,
            missing_vectors=None,
        )

    documents = tuple(
        {
            "document_id": report.get("document_id"),
            "document_version": report.get("document_version"),
            "build_id": report.get("build_id"),
            "status": report.get("status"),
            "failure_reasons": [
                finding.get("code")
                for finding in report.get("findings", [])
                if finding.get("status") == "FAIL"
            ],
            "warning_reasons": [
                finding.get("code")
                for finding in report.get("findings", [])
                if finding.get("status") == "WARNING"
            ],
        }
        for report in sorted(valid, key=lambda item: str(item.get("document_id", "")))
    )
    status = max(
        (str(report.get("status", "FAIL")) for report in valid),
        key=lambda value: _STATUS_RANK.get(value, 2),
        default="PASS",
    )
    return CorpusIngestionEvaluation(
        status=QualityStatus(status),
        generated_at=generated_at or utc_timestamp(),
        document_count=len(valid),
        status_counts={key: status_counts.get(key, 0) for key in _STATUS_RANK},
        totals=totals,
        documents=documents,
        failure_reasons=dict(sorted(failure_reasons.items())),
        scope=scope,
    )


def write_corpus_report(reports_root: Path) -> dict[str, str]:
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(reports_root.glob("*.json"))
        if path.name != "corpus.json"
    ]
    aggregate = aggregate_ingestion_reports(reports)
    payload = aggregate.to_dict()
    store = ArtifactStore(reports_root)
    json_path = store.write_json(Path("corpus.json"), payload)
    markdown_path = store.write_bytes(
        Path("corpus.md"),
        render_corpus_markdown(payload).encode(),
    )
    return {"json": json_path, "markdown": markdown_path}


def render_document_markdown(payload: dict[str, Any]) -> str:
    findings = payload.get("findings", [])
    lines = [
        f"# Ingestion Evaluation — {payload.get('document_id', 'unknown')}",
        "",
        f"Status: **{payload.get('status', 'FAIL')}**",
        "",
        f"Build: `{payload.get('build_id') or 'unavailable'}`",
        f"Scope: `{payload.get('scope', 'full')}`",
        "",
        "## Metrics",
        "",
        f"- Pages: {payload.get('document', {}).get('extracted_pages', 0)} / "
        f"{payload.get('document', {}).get('expected_pages', 0)} extracted",
        f"- Parsing success: {payload.get('document', {}).get('parsing_success_rate', 0):.2%}",
        f"- Pasal: {payload.get('structure', {}).get('pasal_count', 0)}",
        f"- Ayat: {payload.get('structure', {}).get('ayat_count', 0)}",
        f"- Chunks: {payload.get('chunks', {}).get('count', 0)}",
        f"- Embeddings: {payload.get('embedding', {}).get('succeeded', 0)} / "
        f"{payload.get('embedding', {}).get('attempted', 0)} succeeded",
        f"- Vectors: {payload.get('indexing', {}).get('indexed_chunks', 0)} / "
        f"{payload.get('indexing', {}).get('expected_chunks', 0)} indexed",
        "",
        "## Findings",
        "",
    ]
    if payload.get("scope") == "through_metadata":
        lines = [line for line in lines if not line.startswith(("- Embeddings:", "- Vectors:"))]
        lines.insert(
            lines.index("## Findings"),
            "Embedding / indexing: **NOT_RUN** (outside this evaluation).\n",
        )
    if not findings:
        lines.append("No warning or failure findings.")
    for finding in findings:
        lines.append(
            f"- **{finding.get('status')} — {finding.get('code')}**: {finding.get('message')}"
        )
    return "\n".join(lines) + "\n"


def render_corpus_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Corpus Ingestion Evaluation",
        "",
        f"Status: **{payload.get('status', 'FAIL')}**",
        "",
        f"Documents evaluated: {payload.get('document_count', 0)}",
        f"Scope: `{payload.get('scope', 'full')}`",
        "",
        "## Status counts",
        "",
    ]
    for status, count in (payload.get("status_counts") or {}).items():
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Documents", ""])
    for document in payload.get("documents", []):
        reasons = document.get("failure_reasons") or document.get("warning_reasons") or []
        suffix = f" — {', '.join(reasons)}" if reasons else ""
        lines.append(f"- **{document.get('document_id')}**: {document.get('status')}{suffix}")
    return "\n".join(lines) + "\n"


def _payload_status(findings: Sequence[dict[str, Any]]) -> str:
    return max(
        (str(finding.get("status", "FAIL")) for finding in findings),
        key=lambda value: _STATUS_RANK.get(value, 2),
        default="PASS",
    )


def _metric(report: dict[str, Any], group: str, name: str) -> int:
    return int((report.get(group) or {}).get(name, 0) or 0)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
