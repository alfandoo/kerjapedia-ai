from __future__ import annotations

import time
from pathlib import Path

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.chunker import build_chunks
from app.services.ingestion.database import persist_ingestion_result
from app.services.ingestion.embeddings import EmbeddingProvider, HashEmbeddingProvider
from app.services.ingestion.file_validation import validate_pdf_file
from app.services.ingestion.legal_parser import parse_legal_segments
from app.services.ingestion.metadata import find_document, load_manifest
from app.services.ingestion.pdf_extractor import extract_pages
from app.services.ingestion.schemas import EmbeddedChunk, IngestionResult


def document_version_from_checksum(sha256: str) -> int:
    return int(sha256[:8], 16)


def ingest_document(
    project_root: Path,
    metadata_path: Path,
    document_id: str,
    output_dir: Path,
    embedding_provider: EmbeddingProvider | None = None,
    database_session_factory=None,
    vector_store=None,
) -> IngestionResult:
    started_at = time.time()
    manifest = load_manifest(metadata_path)
    documents = manifest["documents"]
    document = find_document(documents, document_id)
    pdf_path = project_root / document.local_file
    artifact_store = ArtifactStore(output_dir)
    warnings: list[str] = []

    validation = validate_pdf_file(pdf_path, document, documents)
    if validation.duplicate_document_ids:
        warnings.append(
            "duplicate_checksum_with=" + ",".join(sorted(validation.duplicate_document_ids))
        )

    version = document_version_from_checksum(validation.sha256)
    raw_pdf_artifact = artifact_store.copy_raw_pdf(pdf_path, document.document_id, version)

    pages = extract_pages(pdf_path)
    ocr_pages = [page.page_number for page in pages if page.requires_ocr]
    if ocr_pages:
        warnings.append(
            "ocr_required_pages="
            + ",".join(str(page_number) for page_number in ocr_pages)
            + "; fallback marked review_required because OCR engine is not configured"
        )

    segments = parse_legal_segments(document.document_id, pages)
    chunks = build_chunks(document, segments, version)

    provider = embedding_provider or HashEmbeddingProvider()
    vectors = provider.embed([chunk.text for chunk in chunks])
    embedded_chunks = [
        EmbeddedChunk(chunk=chunk, embedding_model=provider.model_name, embedding=vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]

    base = Path("documents") / document.document_id / f"v{version}"
    artifacts = {
        "raw_pdf": raw_pdf_artifact,
        "document_metadata": artifact_store.write_json(
            base / "metadata" / "document.json",
            document,
        ),
        "validation": artifact_store.write_json(base / "metadata" / "validation.json", validation),
        "extracted_text": artifact_store.write_json(
            base / "interim" / "extracted_text.json",
            pages,
        ),
        "segments": artifact_store.write_json(base / "processed" / "segments.json", segments),
        "chunks": artifact_store.write_json(base / "processed" / "chunks.json", chunks),
        "embeddings": artifact_store.write_json(
            base / "processed" / "embeddings.json",
            [
                {
                    "chunk_id": item.chunk.chunk_id,
                    "embedding_model": item.embedding_model,
                    "embedding": item.embedding,
                }
                for item in embedded_chunks
            ],
        ),
    }

    requires_review = bool(ocr_pages) or document.verification_status != "verified"
    result = IngestionResult(
        document_id=document.document_id,
        version=version,
        status="review_required" if requires_review else "completed",
        artifacts=artifacts,
        chunk_count=len(chunks),
        pages_processed=len(pages),
        requires_review=requires_review,
        warnings=warnings,
    )

    if vector_store is not None:
        upserted = vector_store.upsert_document(document, version, embedded_chunks)
        result.warnings.append(f"pinecone_upserted_chunks={upserted}")

    log_payload = {
        "result": result,
        "elapsed_seconds": round(time.time() - started_at, 3),
    }
    log_path = Path("logs") / f"{document.document_id}-v{version}.json"
    artifacts["log"] = artifact_store.write_json(log_path, log_payload)

    if database_session_factory is not None:
        with database_session_factory() as session:
            persist_ingestion_result(session, document, result, embedded_chunks)

    return result
