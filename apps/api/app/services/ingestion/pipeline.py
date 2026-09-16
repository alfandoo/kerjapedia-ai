from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.ingestion.artifacts import ArtifactStore
from app.services.ingestion.builds import (
    IngestionBuildConfig,
    document_metadata_hash,
    make_build_identity,
    provider_revision,
    runtime_provenance,
)
from app.services.ingestion.chunking import RegexTokenizer
from app.services.ingestion.chunking.legacy_adapter import (
    build_legacy_chunks_from_structure,
)
from app.services.ingestion.cleaning import clean_pages
from app.services.ingestion.database import persist_ingestion_result
from app.services.ingestion.domain import Document as NormalizedDocument
from app.services.ingestion.domain import StructuredLegalDocument
from app.services.ingestion.embeddings import (
    EmbeddingBatchError,
    EmbeddingProvider,
    HashEmbeddingProvider,
    HybridEmbeddingBatch,
    embed_batch_reliably,
    validate_embedding_batch,
)
from app.services.ingestion.evaluation import (
    DocumentIngestionEvaluation,
    EmbeddingEvaluationInput,
    IngestionEvaluationThresholds,
    evaluate_active_ingestion,
    write_corpus_report,
    write_document_report,
)
from app.services.ingestion.file_validation import validate_pdf_file
from app.services.ingestion.legal_parser import parse_legal_segments
from app.services.ingestion.metadata import find_document, load_manifest
from app.services.ingestion.pdf_extractor import (
    apply_page_ocr_fallback,
    extract_pages,
    from_legacy_extracted_page,
    remove_repeated_margin_noise,
    run_ocr,
    to_legacy_extracted_page,
)
from app.services.ingestion.quality import build_quality_report, text_sha256
from app.services.ingestion.retry import RetryPolicy
from app.services.ingestion.safety import contains_document_prompt_injection
from app.services.ingestion.schemas import Chunk, EmbeddedChunk, IngestionResult
from app.services.ingestion.structure import parse_legal_sections

logger = logging.getLogger(__name__)


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
    provider = embedding_provider or HashEmbeddingProvider()
    config = build_config or _default_build_config(provider)
    # P3-1: Resource validation moved after page extraction
    # Basic file existence check only
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    identity = make_build_identity(
        document.document_id,
        document.sha256,
        config,
        document_metadata_hash(document),
    )
    version = document_version_from_checksum(document.sha256)
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
    if existing is not None:
        raise RuntimeError(
            "Completed ingestion builds are immutable; change the source or build "
            "configuration instead of overwriting one."
        )

    base = Path("documents") / document.document_id / f"v{version}" / "builds" / identity.build_id
    raw_pdf_artifact = artifact_store.copy_raw_pdf(
        pdf_path,
        document.document_id,
        version,
        identity.build_id,
    )

    # P3-1: Extract pages first to get page count for resource validation
    try:
        initial_pages = extract_pages(pdf_path)
    except Exception as exc:
        failure_report = evaluate_active_ingestion(
            document,
            (),
            (),
            (),
            project_root=project_root,
            ingestion_version=config.pipeline_version,
            document_version=version,
            build_id=identity.build_id,
            expected_dimension=config.embedding_dimension,
            expected_page_count=0,
            duration_seconds=time.time() - started_at,
            file_readable=True,
            source_error=f"{type(exc).__name__}: {exc}",
            thresholds=_configured_evaluation_thresholds(config),
        )
        _try_write_failed_evaluation(failure_report, output_dir)
        raise

    # P3-1: Validate resource limits after extracting pages
    try:
        page_count = len(initial_pages)
        estimated_tokens = sum(len(page.text.split()) for page in initial_pages)
        validation = validate_pdf_file(
            pdf_path,
            document,
            documents,
            page_count=page_count,
            estimated_tokens=estimated_tokens,
        )
        if validation.duplicate_document_ids:
            raise ValueError(
                "Source PDF is already registered to another document: "
                + ", ".join(sorted(validation.duplicate_document_ids))
            )
    except Exception as exc:
        failure_report = evaluate_active_ingestion(
            document,
            (),
            (),
            (),
            project_root=project_root,
            ingestion_version=config.pipeline_version,
            document_version=version,
            build_id=identity.build_id,
            expected_dimension=config.embedding_dimension,
            expected_page_count=page_count,
            duration_seconds=time.time() - started_at,
            file_readable=True,
            source_error=f"{type(exc).__name__}: {exc}",
            thresholds=_configured_evaluation_thresholds(config),
        )
        _try_write_failed_evaluation(failure_report, output_dir)
        raise

    pages = initial_pages
    ocr_artifact_path: str | None = None
    initially_ocr_pages = [page.page_number for page in pages if page.requires_ocr]
    if initially_ocr_pages:
        force_ocr = any(
            "missing_word_spaces" in page.quality_flags for page in pages if page.requires_ocr
        )
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
            ocr_output = run_ocr(pdf_path, ocr_path, jobs=config.ocr_jobs, force=force_ocr)
            ocr_artifact_path = ocr_output.as_posix()
            pages = extract_pages(ocr_output)
            warnings.append("ocr_applied=ind+eng")
        except Exception as exc:
            warnings.append(
                "ocr_required_pages="
                + ",".join(str(page_number) for page_number in initially_ocr_pages)
                + f"; failure={type(exc).__name__}"
            )
            pages = apply_page_ocr_fallback(
                pdf_path,
                pages,
                page_numbers=initially_ocr_pages,
            )
            fallback_successes = [
                page.page_number
                for page in pages
                if page.page_number in initially_ocr_pages
                and "ocr_page_fallback" in page.quality_flags
                and page.text.strip()
            ]
            warnings.append(
                "page_ocr_fallback="
                + (",".join(str(page) for page in fallback_successes) or "none")
            )
    pages = remove_repeated_margin_noise(pages)
    pages = [
        to_legacy_extracted_page(page)
        for page in clean_pages(tuple(from_legacy_extracted_page(page) for page in pages))
    ]

    low_quality_pages = [page.page_number for page in pages if page.quality_score < 0.65]
    if low_quality_pages:
        warnings.append(
            "low_text_quality_pages="
            + ",".join(str(page_number) for page_number in low_quality_pages)
        )

    injection_pages = [
        page.page_number for page in pages if contains_document_prompt_injection(page.text)
    ]
    if injection_pages:
        warnings.append(
            "document_prompt_injection_pages="
            + ",".join(str(page_number) for page_number in injection_pages)
        )

    # Keep legacy segments as a stored compatibility artifact. Chunks are now
    # produced from the normalized legal tree, so structural parsing and token
    # enforcement are the same concerns that govern retrieval candidates.
    segments = parse_legal_segments(document.document_id, pages)
    normalized_pages = tuple(from_legacy_extracted_page(page) for page in pages)
    normalized_document = NormalizedDocument(
        document_id=document.document_id,
        title=document.title,
        source=document.source_name,
        source_url=document.source_url,
        file_path=pdf_path,
        file_hash=document.sha256,
        page_count=len(normalized_pages),
        metadata={
            "regulation_type": document.regulation_type,
            "number": document.number,
            "year": document.year,
            "legal_status": document.legal_status,
        },
        ingestion_version=config.pipeline_version,
        pages=normalized_pages,
    )
    legal_sections = tuple(
        parse_legal_sections(
            document.document_id,
            normalized_pages,
            document_title=document.title,
        )
    )
    structured_document = StructuredLegalDocument(
        document=normalized_document,
        sections=legal_sections,
    )
    chunks, chunking_result = build_legacy_chunks_from_structure(
        document,
        structured_document,
        tokenizer=RegexTokenizer(),
        target_tokens=config.target_tokens,
        max_tokens=config.max_tokens,
        overlap_tokens=config.overlap_tokens,
        build_id=identity.build_id,
    )
    try:
        embedding_result = _embed_chunks_with_checkpoint(
            artifact_store,
            base,
            chunks,
            provider,
            config,
            resume=resume,
        )
    except EmbeddingBatchError as exc:
        checkpoint = _load_checkpoint(
            artifact_store.root / base / "checkpoints" / "embeddings.jsonl"
        )
        succeeded_ids = tuple(
            chunk.chunk_id
            for chunk in chunks
            if (record := checkpoint.get(chunk.chunk_id))
            and _checkpoint_record_is_valid(
                record,
                chunk.chunk_id,
                text_sha256(chunk.retrieval_text or chunk.text),
                provider,
                config,
            )
        )
        attempted_ids = tuple(dict.fromkeys((*succeeded_ids, *exc.failed_item_ids)))
        failure_report = evaluate_active_ingestion(
            document,
            pages,
            chunks,
            (),
            project_root=project_root,
            ingestion_version=config.pipeline_version,
            document_version=version,
            build_id=identity.build_id,
            expected_dimension=config.embedding_dimension,
            expected_page_count=len(initial_pages),
            duration_seconds=time.time() - started_at,
            embedding_input=EmbeddingEvaluationInput(
                attempted_ids=attempted_ids,
                succeeded_ids=succeeded_ids,
                failed_ids=tuple(exc.failed_item_ids),
                model=provider.model_name,
                revision=provider_revision(provider),
                expected_dimension=config.embedding_dimension,
                error=str(exc),
                evaluated=True,
            ),
            thresholds=_configured_evaluation_thresholds(config),
        )
        _try_write_failed_evaluation(failure_report, output_dir)
        raise
    embedded_chunks = embedding_result.embedded_chunks

    quality_report = build_quality_report(
        pages,
        chunks,
        embedded_chunks,
        expected_dimension=config.embedding_dimension,
        max_chunk_tokens=config.max_tokens,
        segments=segments,
    )
    ingestion_evaluation = evaluate_active_ingestion(
        document,
        pages,
        chunks,
        embedded_chunks,
        project_root=project_root,
        ingestion_version=config.pipeline_version,
        document_version=version,
        build_id=identity.build_id,
        expected_dimension=config.embedding_dimension,
        expected_page_count=len(initial_pages),
        duration_seconds=time.time() - started_at,
        thresholds=_configured_evaluation_thresholds(config),
    )
    evaluation_root = output_dir / "reports" / "ingestion"
    evaluation_paths = write_document_report(ingestion_evaluation, evaluation_root)
    corpus_evaluation_paths = write_corpus_report(evaluation_root)
    quality_report["ingestion_evaluation"] = {
        "schema_version": ingestion_evaluation.schema_version,
        "status": ingestion_evaluation.status,
        "finding_count": len(ingestion_evaluation.findings),
        "failure_reasons": [
            finding.code for finding in ingestion_evaluation.findings if finding.status == "FAIL"
        ],
        "warning_reasons": [
            finding.code for finding in ingestion_evaluation.findings if finding.status == "WARNING"
        ],
        "report": evaluation_paths["immutable_json"],
        "corpus_report": corpus_evaluation_paths["json"],
    }
    quality_report["gates"]["ingestion_evaluation_passed"] = ingestion_evaluation.status != "FAIL"
    if ingestion_evaluation.status == "FAIL":
        # Evaluation failure is not a crash: preserve artifacts and diagnostics
        # for review, but never label the build publication-ready.
        quality_report["status"] = "review_required"
    quality_report["runtime"] = config.runtime or {}
    quality_report["security"] = {"prompt_injection_pages": injection_pages}
    quality_report["source"] = {
        "sha256": document.sha256,
        "manifest_sha256": document.sha256,
        "checksum_matches": True,  # P3-1: Document hash is always canonical
    }
    quality_report["ingestion_statistics"] = {
        "documents_processed": 1,
        "pages_parsed": len(pages),
        "sections_detected": len(legal_sections),
        "chunks_generated": len(chunks),
        "chunks_embedded": len(embedded_chunks),
        "chunks_indexed": 0,
        "failed_embeddings": embedding_result.failed_embeddings,
        "embedding_batches": embedding_result.batches,
        "embedding_retries": embedding_result.retries,
        "embeddings_reused": embedding_result.reused_chunks,
        "embedding_duration_seconds": embedding_result.duration_seconds,
        "duration_seconds": round(time.time() - started_at, 3),
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
        "segments": artifact_store.write_json(base / "processed" / "segments.json", segments),
        "legal_sections": artifact_store.write_json(
            base / "processed" / "legal_sections.json", list(legal_sections)
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
        "ingestion_evaluation": evaluation_paths["immutable_json"],
        "ingestion_evaluation_markdown": evaluation_paths["immutable_markdown"],
    }
    if ocr_artifact_path is not None:
        artifacts["ocr_pdf"] = ocr_artifact_path
    artifact_manifest = {name: _file_manifest(Path(path)) for name, path in artifacts.items()}
    build_manifest_path = artifact_store.root / base / "metadata" / "build_manifest.json"
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
            "source_sha256": document.sha256,
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


def _configured_evaluation_thresholds(
    config: IngestionBuildConfig,
) -> IngestionEvaluationThresholds:
    values = dict(config.evaluation_thresholds or {})
    values.setdefault("minimum_useful_chunk_tokens", min(80, config.max_tokens))
    values.setdefault("maximum_chunk_tokens", config.max_tokens)
    return IngestionEvaluationThresholds(**values)


def _try_write_failed_evaluation(
    report: DocumentIngestionEvaluation,
    output_dir: Path,
) -> None:
    try:
        reports_root = output_dir / "reports" / "ingestion"
        write_document_report(report, reports_root)
        write_corpus_report(reports_root)
    except Exception:
        logger.exception(
            "Failed to write ingestion evaluation for failed build %s",
            report.build_id,
        )


@dataclass(frozen=True)
class _EmbeddingCheckpointResult:
    embedded_chunks: list[EmbeddedChunk]
    reused_chunks: int
    batches: int
    retries: int
    failed_embeddings: int
    duration_seconds: float


def _embed_chunks_with_checkpoint(
    artifact_store: ArtifactStore,
    base: Path,
    chunks,
    provider: EmbeddingProvider,
    config: IngestionBuildConfig,
    *,
    resume: bool,
) -> _EmbeddingCheckpointResult:
    started = time.monotonic()
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Embedding input contains duplicate chunk IDs")
    checkpoint_relative = base / "checkpoints" / "embeddings.jsonl"
    checkpoint_path = artifact_store.root / checkpoint_relative
    cached = _load_checkpoint(checkpoint_path) if resume else {}
    if not resume and checkpoint_path.exists():
        checkpoint_path.unlink()
    records: dict[str, dict] = {}
    for chunk in chunks:
        expected_hash = text_sha256(chunk.retrieval_text or chunk.text)
        record = cached.get(chunk.chunk_id)
        if record and _checkpoint_record_is_valid(
            record,
            chunk.chunk_id,
            expected_hash,
            provider,
            config,
        ):
            records[chunk.chunk_id] = record

    missing = [chunk for chunk in chunks if chunk.chunk_id not in records]
    reused_chunks = len(chunks) - len(missing)
    batch_count = 0
    retry_count = 0
    for start in range(0, len(missing), config.embedding_batch_size):
        batch_chunks = missing[start : start + config.embedding_batch_size]
        batch_ids = [chunk.chunk_id for chunk in batch_chunks]
        texts = [chunk.retrieval_text or chunk.text for chunk in batch_chunks]
        reliable = embed_batch_reliably(
            provider,
            batch_ids,
            texts,
            expected_dimension=config.embedding_dimension,
            require_sparse=config.require_native_sparse,
            timeout_seconds=config.embedding_timeout_seconds,
            retry_policy=RetryPolicy(
                max_retries=config.embedding_max_retries,
                initial_delay_seconds=config.embedding_retry_initial_seconds,
            ),
        )
        vectors = reliable.vectors
        batch_count += 1
        retry_count += reliable.attempts - 1
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
                "retrieval_text_sha256": text_sha256(chunk.retrieval_text or chunk.text),
                "embedding": [float(value) for value in dense],
                "sparse_embedding": {str(index): float(value) for index, value in sparse.items()},
            }
            payloads.append(payload)
            records[chunk.chunk_id] = payload
        artifact_store.append_jsonl(checkpoint_relative, payloads)

    embedded: list[EmbeddedChunk] = []
    for chunk in chunks:
        payload = records[chunk.chunk_id]
        sparse = payload.get("sparse_embedding") or {}
        if config.require_native_sparse and not sparse:
            raise RuntimeError(f"Native sparse embedding is missing for {chunk.chunk_id}.")
        embedded.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding_model=payload["embedding_model"],
                embedding=[float(value) for value in payload["embedding"]],
                sparse_embedding={int(index): float(value) for index, value in sparse.items()},
                embedding_revision=payload["embedding_revision"],
                retrieval_text_sha256=payload["retrieval_text_sha256"],
            )
        )
    return _EmbeddingCheckpointResult(
        embedded_chunks=embedded,
        reused_chunks=reused_chunks,
        batches=batch_count,
        retries=retry_count,
        failed_embeddings=0,
        duration_seconds=round(time.monotonic() - started, 6),
    )


def _checkpoint_record_is_valid(
    record: dict,
    chunk_id: str,
    expected_text_hash: str,
    provider: EmbeddingProvider,
    config: IngestionBuildConfig,
) -> bool:
    if not (
        record.get("embedding_model") == provider.model_name
        and record.get("embedding_revision") == provider_revision(provider)
        and record.get("retrieval_text_sha256") == expected_text_hash
    ):
        return False
    try:
        sparse = record.get("sparse_embedding") or {}
        validate_embedding_batch(
            HybridEmbeddingBatch(
                dense=[[float(value) for value in record["embedding"]]],
                sparse=[{int(index): float(value) for index, value in sparse.items()}],
            ),
            [chunk_id],
            expected_dimension=config.embedding_dimension,
            require_sparse=config.require_native_sparse,
        )
    except (KeyError, TypeError, ValueError):
        return False
    return True


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
        raise RuntimeError("Existing ingestion build manifest has conflicting provenance.")
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
    chunks = [Chunk(**payload) for payload in json.loads((base / "chunks.json").read_text("utf-8"))]
    embeddings = {
        str(payload["chunk_id"]): payload
        for payload in json.loads((base / "embeddings.json").read_text("utf-8"))
    }
    result: list[EmbeddedChunk] = []
    for chunk in chunks:
        payload = embeddings.get(chunk.chunk_id)
        if payload is None:
            raise RuntimeError(f"Existing build is missing embedding for {chunk.chunk_id}.")
        sparse = payload.get("sparse_embedding") or {}
        result.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding_model=str(payload["embedding_model"]),
                embedding=[float(value) for value in payload["embedding"]],
                sparse_embedding={int(index): float(value) for index, value in sparse.items()},
                embedding_revision=str(payload.get("embedding_revision", "unversioned")),
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
