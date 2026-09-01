from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.builds import (
    IngestionBuildConfig,
    make_build_identity,
    provider_revision,
    runtime_provenance,
)
from app.services.ingestion.chunker import build_chunks
from app.services.ingestion.database import persist_ingestion_result
from app.services.ingestion.embeddings import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    embed_hybrid,
)
from app.services.ingestion.file_validation import validate_pdf_file
from app.services.ingestion.legal_parser import parse_legal_segments
from app.services.ingestion.metadata import find_document, load_manifest
from app.services.ingestion.pdf_extractor import (
    extract_pages,
    remove_repeated_margin_noise,
    run_ocr,
)
from app.services.ingestion.quality import build_quality_report, text_sha256
from app.services.ingestion.safety import contains_document_prompt_injection
from app.services.ingestion.schemas import Chunk, EmbeddedChunk, IngestionResult


def document_version_from_checksum(sha256: str) -> int:
    return int(sha256[:8], 16)


def ingest_document(
    project_root: Path,
    metadata_path: Path,
    document_id: str,
    output_dir: Path,
    embedding_provider: EmbeddingProvider | None = None,
    database_session_factory=None,
    extra_manifest_path: Path | None = None,
    job_id: str | None = None,
    build_config: IngestionBuildConfig | None = None,
    resume: bool = True,
) -> IngestionResult:
    started_at = time.time()
    manifest = load_manifest(metadata_path)
    documents = manifest["documents"]
    if extra_manifest_path is not None and extra_manifest_path.exists():
        extra_documents = load_manifest(extra_manifest_path)["documents"]
        by_id = {document.document_id: document for document in documents}
        for document in extra_documents:
            by_id[document.document_id] = document
        documents = list(by_id.values())
    document = find_document(documents, document_id)
    pdf_path = project_root / document.local_file
    artifact_store = ArtifactStore(output_dir)
    warnings: list[str] = []

    validation = validate_pdf_file(pdf_path, document, documents)
    if validation.duplicate_document_ids:
        warnings.append(
            "duplicate_checksum_with="
            + ",".join(sorted(validation.duplicate_document_ids))
        )

    provider = embedding_provider or HashEmbeddingProvider()
    config = build_config or _default_build_config(provider)
    identity = make_build_identity(document.document_id, validation.sha256, config)
    version = document_version_from_checksum(validation.sha256)
    existing = _load_existing_result(
        artifact_store,
        document.document_id,
        version,
        identity.build_id,
        identity.config_hash,
    )
    if resume and existing is not None:
        if database_session_factory is not None:
            existing_embedded = _load_existing_embedded_chunks(
                artifact_store,
                document.document_id,
                version,
                identity.build_id,
            )
            with database_session_factory() as session:
                persist_ingestion_result(
                    session,
                    document,
                    existing,
                    existing_embedded,
                    build_config=config,
                    job_id=job_id,
                )
        return existing

    base = (
        Path("documents")
        / document.document_id
        / f"v{version}"
        / "builds"
        / identity.build_id
    )
    raw_pdf_artifact = artifact_store.copy_raw_pdf(
        pdf_path,
        document.document_id,
        version,
        identity.build_id,
    )

    initial_pages = extract_pages(pdf_path)
    pages = initial_pages
    ocr_artifact_path: str | None = None
    initially_ocr_pages = [page.page_number for page in pages if page.requires_ocr]
    if initially_ocr_pages:
        try:
            ocr_path = (
                artifact_store.document_dir(
                    document.document_id,
                    version,
                    identity.build_id,
                )
                / "interim"
                / "ocr.pdf"
            )
            ocr_output = run_ocr(pdf_path, ocr_path, jobs=config.ocr_jobs)
            ocr_artifact_path = ocr_output.as_posix()
            pages = extract_pages(ocr_output)
            warnings.append("ocr_applied=ind+eng")
        except Exception as exc:
            warnings.append(
                "ocr_required_pages="
                + ",".join(str(page_number) for page_number in initially_ocr_pages)
                + f"; failure={type(exc).__name__}"
            )
    pages = remove_repeated_margin_noise(pages)

    low_quality_pages = [
        page.page_number for page in pages if page.quality_score < 0.65
    ]
    if low_quality_pages:
        warnings.append(
            "low_text_quality_pages="
            + ",".join(str(page_number) for page_number in low_quality_pages)
        )

    injection_pages = [
        page.page_number
        for page in pages
        if contains_document_prompt_injection(page.text)
    ]
    if injection_pages:
        warnings.append(
            "document_prompt_injection_pages="
            + ",".join(str(page_number) for page_number in injection_pages)
        )

    segments = parse_legal_segments(document.document_id, pages)
    chunks = build_chunks(
        document,
        segments,
        version,
        target_tokens=config.target_tokens,
        max_tokens=config.max_tokens,
        overlap_tokens=config.overlap_tokens,
        min_merge_tokens=config.min_merge_tokens,
        parent_tokens=config.parent_tokens,
        build_id=identity.build_id,
    )
    embedded_chunks = _embed_chunks_with_checkpoint(
        artifact_store,
        base,
        chunks,
        provider,
        config,
        resume=resume,
    )

    quality_report = build_quality_report(
        pages,
        chunks,
        embedded_chunks,
        expected_dimension=config.embedding_dimension,
        max_chunk_tokens=config.max_tokens,
        segments=segments,
    )
    quality_report["runtime"] = config.runtime or {}
    quality_report["security"] = {"prompt_injection_pages": injection_pages}
    quality_report["source"] = {
        "sha256": validation.sha256,
        "manifest_sha256": document.sha256,
        "checksum_matches": validation.sha256 == document.sha256,
    }
    if injection_pages:
        quality_report["gates"]["no_document_prompt_injection"] = False
        quality_report["status"] = "review_required"
    else:
        quality_report["gates"]["no_document_prompt_injection"] = True
    if document.verification_status != "verified":
        quality_report["gates"]["source_manifest_verified"] = False
        quality_report["status"] = "review_required"
    else:
        quality_report["gates"]["source_manifest_verified"] = True
    if not all(quality_report["gates"].values()):
        quality_report["status"] = "review_required"

    requires_review = quality_report["status"] != "passed"
    status = "review_required" if requires_review else "completed"
    artifacts = {
        "raw_pdf": raw_pdf_artifact,
        "document_metadata": artifact_store.write_json(
            base / "metadata" / "document.json",
            document,
        ),
        "validation": artifact_store.write_json(
            base / "metadata" / "validation.json",
            validation,
        ),
        "raw_extracted_text": artifact_store.write_json(
            base / "interim" / "raw_extracted_text.json",
            initial_pages,
        ),
        "extracted_text": artifact_store.write_json(
            base / "interim" / "extracted_text.json",
            pages,
        ),
        "segments": artifact_store.write_json(
            base / "processed" / "segments.json", segments
        ),
        "chunks": artifact_store.write_json(base / "processed" / "chunks.json", chunks),
        "embeddings": artifact_store.write_json(
            base / "processed" / "embeddings.json",
            [_embedding_payload(item) for item in embedded_chunks],
        ),
        "quality_report": artifact_store.write_json(
            base / "metadata" / "quality_report.json",
            quality_report,
        ),
    }
    if ocr_artifact_path is not None:
        artifacts["ocr_pdf"] = ocr_artifact_path
    artifact_manifest = {
        name: _file_manifest(Path(path)) for name, path in artifacts.items()
    }
    build_manifest_path = (
        artifact_store.root / base / "metadata" / "build_manifest.json"
    )
    log_path = (
        artifact_store.root
        / "logs"
        / (f"{document.document_id}-v{version}-{identity.build_id}.json")
    )
    artifacts["build_manifest"] = build_manifest_path.as_posix()
    artifacts["log"] = log_path.as_posix()
    result = IngestionResult(
        document_id=document.document_id,
        version=version,
        status=status,
        artifacts=artifacts,
        chunk_count=len(chunks),
        pages_processed=len(pages),
        requires_review=requires_review,
        warnings=warnings,
        build_id=identity.build_id,
        config_hash=identity.config_hash,
        quality_report=quality_report,
        artifact_manifest=artifact_manifest,
    )
    artifact_store.write_json(
        base / "metadata" / "build_manifest.json",
        {
            "build_id": identity.build_id,
            "config_hash": identity.config_hash,
            "config": config.payload(),
            "source_sha256": validation.sha256,
            "artifacts": artifact_manifest,
            "result": asdict(result),
        },
    )
    artifact_store.write_json(
        Path("logs") / log_path.name,
        {
            "result": result,
            "elapsed_seconds": round(time.time() - started_at, 3),
        },
    )

    if database_session_factory is not None:
        with database_session_factory() as session:
            persist_ingestion_result(
                session,
                document,
                result,
                embedded_chunks,
                build_config=config,
                job_id=job_id,
            )

    return result


def _default_build_config(provider: EmbeddingProvider) -> IngestionBuildConfig:
    return IngestionBuildConfig(
        embedding_model=provider.model_name,
        embedding_revision=provider_revision(provider),
        embedding_dimension=int(getattr(provider, "dimensions", 1024)),
        require_native_sparse=bool(getattr(provider, "require_native_sparse", False)),
        embedding_batch_size=int(getattr(provider, "batch_size", 16)),
        runtime=runtime_provenance(),
    )


def _embed_chunks_with_checkpoint(
    artifact_store: ArtifactStore,
    base: Path,
    chunks,
    provider: EmbeddingProvider,
    config: IngestionBuildConfig,
    *,
    resume: bool,
) -> list[EmbeddedChunk]:
    checkpoint_relative = base / "checkpoints" / "embeddings.jsonl"
    checkpoint_path = artifact_store.root / checkpoint_relative
    cached = _load_checkpoint(checkpoint_path) if resume else {}
    if not resume and checkpoint_path.exists():
        checkpoint_path.unlink()
    records: dict[str, dict] = {}
    for chunk in chunks:
        expected_hash = text_sha256(chunk.retrieval_text or chunk.text)
        record = cached.get(chunk.chunk_id)
        if record and (
            record.get("embedding_model") == provider.model_name
            and record.get("embedding_revision") == provider_revision(provider)
            and record.get("retrieval_text_sha256") == expected_hash
        ):
            records[chunk.chunk_id] = record

    missing = [chunk for chunk in chunks if chunk.chunk_id not in records]
    for start in range(0, len(missing), config.embedding_batch_size):
        batch_chunks = missing[start : start + config.embedding_batch_size]
        texts = [chunk.retrieval_text or chunk.text for chunk in batch_chunks]
        vectors = embed_hybrid(provider, texts)
        payloads = []
        for chunk, dense, sparse in zip(
            batch_chunks,
            vectors.dense,
            vectors.sparse,
            strict=True,
        ):
            payload = {
                "chunk_id": chunk.chunk_id,
                "embedding_model": provider.model_name,
                "embedding_revision": provider_revision(provider),
                "retrieval_text_sha256": text_sha256(
                    chunk.retrieval_text or chunk.text
                ),
                "embedding": [float(value) for value in dense],
                "sparse_embedding": {
                    str(index): float(value) for index, value in sparse.items()
                },
            }
            payloads.append(payload)
            records[chunk.chunk_id] = payload
        artifact_store.append_jsonl(checkpoint_relative, payloads)

    embedded: list[EmbeddedChunk] = []
    for chunk in chunks:
        payload = records[chunk.chunk_id]
        sparse = payload.get("sparse_embedding") or {}
        if config.require_native_sparse and not sparse:
            raise RuntimeError(
                f"Native sparse embedding is missing for {chunk.chunk_id}."
            )
        embedded.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding_model=payload["embedding_model"],
                embedding=[float(value) for value in payload["embedding"]],
                sparse_embedding={
                    int(index): float(value) for index, value in sparse.items()
                },
                embedding_revision=payload["embedding_revision"],
                retrieval_text_sha256=payload["retrieval_text_sha256"],
            )
        )
    return embedded


def _load_checkpoint(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    records: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        chunk_id = payload.get("chunk_id")
        if chunk_id:
            records[str(chunk_id)] = payload
    return records


def _load_existing_result(
    artifact_store: ArtifactStore,
    document_id: str,
    version: int,
    build_id: str,
    config_hash: str,
) -> IngestionResult | None:
    path = (
        artifact_store.document_dir(document_id, version, build_id)
        / "metadata"
        / "build_manifest.json"
    )
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("build_id") != build_id or payload.get("config_hash") != config_hash:
        raise RuntimeError(
            "Existing ingestion build manifest has conflicting provenance."
        )
    for manifest in (payload.get("artifacts") or {}).values():
        artifact_path = Path(str(manifest.get("path", "")))
        if not artifact_path.is_file() or _file_manifest(artifact_path) != manifest:
            raise RuntimeError("Existing ingestion build artifact checksum mismatch.")
    result = dict(payload["result"])
    result["artifact_manifest"] = payload.get("artifacts", {})
    return IngestionResult(**result)


def _load_existing_embedded_chunks(
    artifact_store: ArtifactStore,
    document_id: str,
    version: int,
    build_id: str,
) -> list[EmbeddedChunk]:
    base = artifact_store.document_dir(document_id, version, build_id) / "processed"
    chunks = [
        Chunk(**payload)
        for payload in json.loads((base / "chunks.json").read_text("utf-8"))
    ]
    embeddings = {
        str(payload["chunk_id"]): payload
        for payload in json.loads((base / "embeddings.json").read_text("utf-8"))
    }
    result: list[EmbeddedChunk] = []
    for chunk in chunks:
        payload = embeddings.get(chunk.chunk_id)
        if payload is None:
            raise RuntimeError(
                f"Existing build is missing embedding for {chunk.chunk_id}."
            )
        sparse = payload.get("sparse_embedding") or {}
        result.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding_model=str(payload["embedding_model"]),
                embedding=[float(value) for value in payload["embedding"]],
                sparse_embedding={
                    int(index): float(value) for index, value in sparse.items()
                },
                embedding_revision=str(
                    payload.get("embedding_revision", "unversioned")
                ),
                retrieval_text_sha256=payload.get("retrieval_text_sha256"),
            )
        )
    return result


def _embedding_payload(item: EmbeddedChunk) -> dict:
    vector_norm = math.sqrt(sum(float(value) ** 2 for value in item.embedding))
    return {
        "chunk_id": item.chunk.chunk_id,
        "build_id": item.chunk.build_id,
        "embedding_model": item.embedding_model,
        "embedding_revision": item.embedding_revision,
        "dimensions": len(item.embedding),
        "vector_norm": round(vector_norm, 8),
        "retrieval_text_sha256": item.retrieval_text_sha256,
        "embedding": item.embedding,
        "sparse_embedding": item.sparse_embedding,
    }


def _file_manifest(path: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return {"path": path.as_posix(), "sha256": digest.hexdigest(), "size_bytes": size}
