"""Run and persist the ingestion evaluation through metadata, without providers.

Example: python -m app.services.ingestion.evaluation.preembedding --all --ocr
Reports and checkpoints are isolated from completed ingestion builds/releases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.builds import CHUNKER_VERSION, PARSER_VERSION, PIPELINE_VERSION
from app.services.ingestion.chunking import ChunkingConfig, RegexTokenizer, chunk_legal_document
from app.services.ingestion.cleaning import clean_pages
from app.services.ingestion.domain import Document, StructuredLegalDocument
from app.services.ingestion.evaluation.evaluator import evaluate_ingestion
from app.services.ingestion.evaluation.models import EvaluationFinding, QualityStatus
from app.services.ingestion.evaluation.reporting import write_corpus_report, write_document_report
from app.services.ingestion.file_validation import validate_pdf_file
from app.services.ingestion.metadata import load_manifest
from app.services.ingestion.pdf_extractor import (
    apply_page_ocr_fallback,
    assess_text_quality,
    extract_pages,
    from_legacy_extracted_page,
    remove_repeated_margin_noise,
)
from app.services.ingestion.provenance import MetadataContext, enrich_chunk_metadata
from app.services.ingestion.schemas import ExtractedPage
from app.services.ingestion.structure import parse_legal_sections

EXTRACTION_PROFILE = "preembedding-pages-v1"


def prepare_pages(
    source: Path,
    checksum: str,
    store: ArtifactStore,
    *,
    ocr: bool,
    requested_pages: tuple[int, ...] = (),
):
    """Cache complete source pages; repair genuinely unreadable pages selectively."""
    cache_key = f"{checksum}-{EXTRACTION_PROFILE}"
    raw_path = Path("cache") / cache_key / "raw-spatial-v3.json"
    raw_file = store.root / raw_path
    if raw_file.is_file():
        raw_pages = [
            ExtractedPage(**item) for item in json.loads(raw_file.read_text(encoding="utf-8"))
        ]
    else:
        raw_pages = extract_pages(source, detect_tables=False)
        store.write_json(raw_path, raw_pages)
    cleaned = clean_pages(
        [from_legacy_extracted_page(p) for p in remove_repeated_margin_noise(raw_pages)]
    )
    # Line-wrapped born-digital text often becomes readable after reflow;
    # do not OCR an otherwise healthy page solely for having short lines.
    candidates = [
        p.page_number
        for p in cleaned
        if assess_text_quality(p.cleaned_text)[0] < 0.65
        or "replacement_glyphs" in assess_text_quality(p.cleaned_text)[1]
    ]
    if any(number < 1 or number > len(raw_pages) for number in requested_pages):
        raise ValueError("Requested OCR page is outside the source document")
    if requested_pages and not ocr:
        raise ValueError("Explicit OCR pages require --ocr")
    candidates = sorted(set(candidates).union(requested_pages))
    repaired = list(raw_pages)
    attempted = set()
    if ocr:
        for number in candidates:
            attempted.add(number)
            relative = Path("cache") / cache_key / f"ocr-{number}.json"
            cached = store.root / relative
            if cached.is_file():
                page = ExtractedPage(**json.loads(cached.read_text(encoding="utf-8")))
            else:
                page = apply_page_ocr_fallback(
                    source, [raw_pages[number - 1]], page_numbers=[number]
                )[0]
                if "ocr_page_fallback_failed" not in page.quality_flags:
                    store.write_json(relative, page)
            repaired[number - 1] = page
            print(f"  OCR page={number} chars={page.text_length}", flush=True)

    def normalize():
        return clean_pages(
            [from_legacy_extracted_page(p) for p in remove_repeated_margin_noise(repaired)]
        )

    normalized = normalize()
    # OCR can change the repeated-margin evidence. Re-evaluate the final
    # cleaned pages, but attempt each source page at most once per run.
    while ocr:
        remaining = [
            p.page_number
            for p in normalized
            if assess_text_quality(p.cleaned_text)[0] < 0.65 and p.page_number not in attempted
        ]
        if not remaining:
            break
        for number in remaining:
            attempted.add(number)
            candidates.append(number)
            relative = Path("cache") / cache_key / f"ocr-{number}.json"
            cached = store.root / relative
            page = (
                ExtractedPage(**json.loads(cached.read_text(encoding="utf-8")))
                if cached.is_file()
                else apply_page_ocr_fallback(
                    source, [raw_pages[number - 1]], page_numbers=[number]
                )[0]
            )
            if "ocr_page_fallback_failed" not in page.quality_flags:
                store.write_json(relative, page)
            repaired[number - 1] = page
            print(f"  OCR final-clean page={number} chars={page.text_length}", flush=True)
        normalized = normalize()
    pages = []
    for page in normalized:
        score, flags = assess_text_quality(page.cleaned_text)
        metadata = {**page.metadata, "quality_score": score, "requires_ocr": score < 0.65}
        metadata["quality_flags"] = list(
            dict.fromkeys([*metadata.get("quality_flags", []), *flags])
        )
        pages.append(replace(page, metadata=metadata))
    return tuple(pages), candidates


def run_document(
    root: Path,
    document,
    documents,
    output: Path,
    *,
    ocr: bool,
    requested_pages: tuple[int, ...] = (),
):
    started = time.monotonic()
    source = root / document.local_file
    validation = validate_pdf_file(source, document, documents)
    store = ArtifactStore(output)
    pages, candidates = prepare_pages(
        source, validation.sha256, store, ocr=ocr, requested_pages=requested_pages
    )
    normalized = Document(
        document_id=document.document_id,
        title=document.title,
        source=document.source_name,
        source_url=document.source_url,
        file_path=source,
        file_hash=validation.sha256,
        page_count=len(pages),
        metadata=asdict(document),
        ingestion_version=PIPELINE_VERSION,
        pages=pages,
    )
    sections = tuple(
        parse_legal_sections(document.document_id, pages, document_title=document.title)
    )
    structured = StructuredLegalDocument(normalized, sections)
    result = chunk_legal_document(structured, tokenizer=RegexTokenizer(), config=ChunkingConfig())
    context = MetadataContext(
        parser_version=PARSER_VERSION,
        chunker_version=CHUNKER_VERSION,
        embedding_model="not-generated",
        created_at=datetime.now(UTC),
    )
    metadata_error = None
    try:
        chunks = enrich_chunk_metadata(structured, result.chunks, context)
    except ValueError as exc:
        chunks = result.chunks
        metadata_error = str(exc)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "document": asdict(document),
                "pipeline": PIPELINE_VERSION,
                "parser": PARSER_VERSION,
                "chunker": CHUNKER_VERSION,
                "page_hashes": [hashlib.sha256(p.cleaned_text.encode()).hexdigest() for p in pages],
                "scope": "through_metadata",
                "ocr": ocr,
                "requested_ocr_pages": requested_pages,
                "implementation": hashlib.sha256(
                    b"".join(
                        path.read_bytes()
                        for path in sorted(Path(__file__).parents[1].rglob("*.py"))
                    )
                ).hexdigest(),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]
    build_id = f"pre_{fingerprint}"
    report = evaluate_ingestion(
        normalized,
        sections,
        chunks,
        scope="through_metadata",
        build_id=build_id,
        expected_page_count=len(pages),
        duration_seconds=time.monotonic() - started,
    )
    extra = []
    if metadata_error:
        extra.append(
            EvaluationFinding(
                "metadata.validation_failed", QualityStatus.FAIL, "metadata", metadata_error
            )
        )
    unresolved = [str(p.page_number) for p in pages if p.metadata.get("requires_ocr")]
    if unresolved:
        extra.append(
            EvaluationFinding(
                "page.ocr_unresolved",
                QualityStatus.FAIL,
                "page",
                "Pages remain unreadable or require review.",
                affected_items=tuple(unresolved),
            )
        )
    if not any(s.type == "pasal" for s in sections):
        extra.append(
            EvaluationFinding(
                "structure.no_articles",
                QualityStatus.FAIL,
                "structure",
                "No Pasal detected in a regulation.",
            )
        )
    if extra:
        report = replace(report, status=QualityStatus.FAIL, findings=(*report.findings, *extra))
    base = Path("artifacts") / document.document_id / build_id
    store.write_json(base / "pages.json", pages)
    store.write_json(base / "sections.json", sections)
    store.write_json(base / "chunks.json", chunks)
    store.write_json(base / "validation.json", validation)
    store.write_json(
        base / "manifest.json",
        {
            "scope": report.scope,
            "ocr_candidates": sorted(candidates),
            "ocr_enabled": ocr,
            "requested_ocr_pages": requested_pages,
            "table_detection": "not_run",
            "tokenizer": RegexTokenizer.name,
            "embedding": "NOT_RUN",
            "indexing": "NOT_RUN",
        },
    )
    write_document_report(report, output / "reports")
    print(
        f"{document.document_id}: {report.status} pages={len(pages)} "
        f"chunks={len(chunks)} findings={[f.code for f in report.findings]}",
        flush=True,
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument(
        "--ocr-page",
        action="append",
        default=[],
        metavar="DOCUMENT_ID:PAGE",
        help="Re-extract a source-verified suspect page; never override evaluation status",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not args.all and not args.document_id:
        parser.error("Choose --all or --document-id")
    root = Path(__file__).resolve().parents[6]
    output = args.output_dir or root / "storage/ingestion/preembedding"
    docs = load_manifest(root / "dataset/metadata.json")["documents"]
    requests = {}
    for value in args.ocr_page:
        try:
            identifier, number = value.rsplit(":", 1)
            requests.setdefault(identifier, set()).add(int(number))
        except ValueError:
            parser.error("--ocr-page requires DOCUMENT_ID:PAGE")
    known = {doc.document_id for doc in docs}
    if set(requests) - known or set(args.document_id or []) - known:
        parser.error("Unknown document ID")
    for doc in docs:
        if args.all or doc.document_id in args.document_id:
            print(f"Preparing {doc.document_id}", flush=True)
            run_document(
                root,
                doc,
                docs,
                output,
                ocr=args.ocr,
                requested_pages=tuple(sorted(requests.get(doc.document_id, ()))),
            )
    paths = write_corpus_report(output / "reports")
    print(json.dumps(paths), flush=True)


if __name__ == "__main__":
    main()
