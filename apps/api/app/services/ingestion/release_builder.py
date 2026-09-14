from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.db.session import create_session
from app.models.ingestion import (
    Document,
    DocumentRelationship,
    DocumentVersion,
    IngestionBuild,
    RagIndexRelease,
)
from app.services.answering.prompts import PROMPT_VERSION_ID
from app.services.ingestion.evaluation import (
    finalize_indexing_report,
    write_corpus_report,
)
from app.services.ingestion.governance import is_canonical_official_source_url
from app.services.ingestion.schemas import Chunk, DocumentMetadata, EmbeddedChunk
from app.services.ingestion.vector_indexing import (
    VectorIndexConfig,
    VectorIndexingError,
    clear_namespace_reliably,
    expected_vector_metadata,
    index_document_reliably,
    verify_indexed_vectors,
)
from app.services.providers import pinecone_store_from_settings
from app.services.retrieval.relationships import relationship_snapshot_hash


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_index_release(release_id: str, storage_root: Path) -> dict[str, Any]:
    started = time.monotonic()
    with create_session() as session:
        release = (
            session.query(RagIndexRelease)
            .filter(RagIndexRelease.release_id == release_id)
            .with_for_update()
            .one_or_none()
        )
        if release is None:
            raise RuntimeError("RAG index release was not found.")
        if release.status != "building":
            raise RuntimeError("Only a release in the building lifecycle can be built.")
        if release.build_status == "succeeded":
            return dict(release.build_summary or {})
        if release.build_status == "running":
            raise RuntimeError("RAG index release build is already running.")
        release_namespace = str(release.namespace)
        release.build_status = "running"
        release.build_summary = {}
        session.commit()

    index_config = VectorIndexConfig(
        batch_size=settings.pinecone_upsert_batch_size,
        timeout_seconds=settings.pinecone_write_timeout_seconds,
        max_retries=settings.pinecone_write_max_retries,
        retry_initial_seconds=settings.ingestion_embedding_retry_initial_seconds,
    )
    store = None
    statistics: dict[str, int | float] = {
        "documents_processed": 0,
        "pages_parsed": 0,
        "sections_detected": 0,
        "chunks_generated": 0,
        "chunks_embedded": 0,
        "chunks_indexed": 0,
        "failed_embeddings": 0,
        "vector_batches": 0,
        "vector_retries": 0,
    }
    expected_metadata: dict[str, dict[str, object]] = {}
    document_index_reports: list[tuple[str, str, list[str]]] = []
    try:
        with create_session() as session:
            release = session.get(RagIndexRelease, release_id)
            if release is None:
                raise RuntimeError("RAG index release was not found.")
            if {
                "embedding": release.embedding_model,
                "reranker": release.reranker_model,
                "generator": release.generator_model,
                "verifier": release.verifier_model,
                "prompt": release.prompt_version_id,
            } != {
                "embedding": settings.embedding_model,
                "reranker": settings.reranker_model,
                "generator": settings.openrouter_model,
                "verifier": settings.claim_verifier_model,
                "prompt": PROMPT_VERSION_ID,
            }:
                raise RuntimeError(
                    "Release model provenance does not match build runtime."
                )
            if release.relationship_snapshot_hash != relationship_snapshot_hash(
                session.query(DocumentRelationship).all()
            ):
                raise RuntimeError("Release legal-relationship snapshot is stale.")

            store = pinecone_store_from_settings(
                settings,
                namespace=release.namespace,
                allow_unpublished=False,
            )
            statistics["vector_retries"] += clear_namespace_reliably(
                store,
                config=index_config,
            )
            version_rows = _release_versions(session, release)
            for version_row in version_rows:
                document = session.get(Document, version_row.document_id)
                if document is None:
                    raise RuntimeError(
                        f"Document registry missing {version_row.document_id}."
                    )
                is_current = (
                    release.document_versions.get(version_row.document_id)
                    == version_row.version
                )
                if not _version_is_eligible(version_row, historical=not is_current):
                    raise RuntimeError(
                        f"Document version is no longer eligible: {version_row.version_id}."
                    )
                build_id = (release.ingestion_builds or {}).get(version_row.version_id)
                build = session.get(IngestionBuild, build_id) if build_id else None
                if not _build_is_eligible(build, version_row):
                    raise RuntimeError(
                        f"Approved ingestion build is missing or stale: {version_row.version_id}."
                    )
                _validate_artifact_provenance(storage_root, version_row, build)
                embedded = _load_embedded_chunks(
                    storage_root,
                    version_row.document_id,
                    int(version_row.version),
                    build.build_id,
                )
                if any(
                    item.embedding_model != release.embedding_model
                    or item.embedding_revision != settings.embedding_model_revision
                    or len(item.embedding) != settings.embedding_dimension
                    or not item.sparse_embedding
                    for item in embedded
                ):
                    raise RuntimeError(
                        f"Hybrid embedding artifact mismatch for {version_row.version_id}."
                    )
                metadata = DocumentMetadata(
                    document_id=document.document_id,
                    title=document.title,
                    short_title=document.short_title,
                    regulation_type=document.regulation_type,
                    number=document.number,
                    year=document.year,
                    issuer=document.issuer,
                    topics=list(document.topics),
                    legal_status=version_row.legal_status,
                    source_name="Database registry",
                    source_url=version_row.source_url,
                    local_file=version_row.local_file,
                    file_name=Path(version_row.local_file).name,
                    size_bytes=version_row.size_bytes,
                    sha256=version_row.sha256,
                    verification_status=version_row.source_verification_status,
                )
                build_statistics = (build.quality_report or {}).get(
                    "ingestion_statistics"
                ) or {}
                statistics["documents_processed"] += 1
                statistics["pages_parsed"] += int(
                    build_statistics.get(
                        "pages_parsed",
                        ((build.quality_report or {}).get("pages") or {}).get("count", 0),
                    )
                )
                statistics["sections_detected"] += int(
                    build_statistics.get(
                        "sections_detected",
                        ((build.quality_report or {}).get("chunks") or {}).get(
                            "detected_article_count", 0
                        ),
                    )
                )
                statistics["chunks_generated"] += int(
                    build_statistics.get("chunks_generated", len(embedded))
                )
                statistics["chunks_embedded"] += len(embedded)
                statistics["failed_embeddings"] += int(
                    build_statistics.get("failed_embeddings", 0)
                )
                for item in embedded:
                    if item.chunk.chunk_id in expected_metadata:
                        raise VectorIndexingError(
                            "Release contains duplicate vector IDs",
                            failed_item_ids=[item.chunk.chunk_id],
                        )
                    expected_metadata[item.chunk.chunk_id] = expected_vector_metadata(
                        metadata,
                        item,
                    )
                document_index_reports.append(
                    (
                        version_row.document_id,
                        build.build_id,
                        [item.chunk.chunk_id for item in embedded],
                    )
                )
                index_stats = index_document_reliably(
                    store,
                    metadata,
                    int(version_row.version),
                    embedded,
                    expected_model=release.embedding_model,
                    expected_revision=settings.embedding_model_revision,
                    expected_dimension=settings.embedding_dimension,
                    config=index_config,
                    publication_status=version_row.publication_status,
                    source_verification_status=version_row.source_verification_status,
                    legal_review_status=version_row.legal_review_status,
                    is_current=(
                        release.document_versions.get(version_row.document_id)
                        == version_row.version
                    ),
                )
                statistics["chunks_indexed"] += index_stats.indexed_chunks
                statistics["vector_batches"] += index_stats.batches
                statistics["vector_retries"] += index_stats.retries
            verify_indexed_vectors(
                store,
                expected_metadata,
                config=index_config,
            )
            if statistics["chunks_indexed"] != len(expected_metadata):
                raise VectorIndexingError(
                    "Release indexed count does not match its expected chunk manifest",
                    failed_item_ids=list(expected_metadata),
                )
            manifest_checksum = hashlib.sha256(
                json.dumps(
                    expected_metadata,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            report_errors: list[str] = []
            reports_root = storage_root / "reports" / "ingestion"
            for document_id, report_build_id, vector_ids in document_index_reports:
                try:
                    finalize_indexing_report(
                        reports_root,
                        document_id=document_id,
                        build_id=report_build_id,
                        expected_ids=vector_ids,
                        indexed_ids=vector_ids,
                        namespace=release.namespace,
                        release_id=release.release_id,
                    )
                except Exception as report_exc:
                    report_errors.append(
                        f"{document_id}:{type(report_exc).__name__}"
                    )
            try:
                write_corpus_report(reports_root)
            except Exception as report_exc:
                report_errors.append(f"corpus:{type(report_exc).__name__}")
            release.build_status = "succeeded"
            release.build_summary = {
                **statistics,
                "document_count": len({row.document_id for row in version_rows}),
                "version_count": len(version_rows),
                "chunk_count": statistics["chunks_indexed"],
                "expected_vector_count": len(expected_metadata),
                "verified_vector_count": len(expected_metadata),
                "embedding_model": release.embedding_model,
                "embedding_revision": settings.embedding_model_revision,
                "vector_dimension": settings.embedding_dimension,
                "vector_manifest_checksum": manifest_checksum,
                "ingestion_evaluation_report_errors": report_errors,
                "duration_seconds": round(time.monotonic() - started, 3),
                "ingestion_builds": dict(release.ingestion_builds or {}),
            }
            session.commit()
            return release.build_summary
    except Exception as exc:
        cleanup_error: str | None = None
        if store is not None:
            try:
                clear_namespace_reliably(store, config=index_config)
            except Exception as cleanup_exc:
                cleanup_error = type(cleanup_exc).__name__
        evaluation_report_errors: list[str] = []
        reports_root = storage_root / "reports" / "ingestion"
        if cleanup_error is None:
            for document_id, report_build_id, vector_ids in document_index_reports:
                try:
                    finalize_indexing_report(
                        reports_root,
                        document_id=document_id,
                        build_id=report_build_id,
                        expected_ids=vector_ids,
                        indexed_ids=(),
                        namespace=release_namespace,
                        release_id=release_id,
                    )
                except Exception as report_exc:
                    evaluation_report_errors.append(
                        f"{document_id}:{type(report_exc).__name__}"
                    )
        else:
            evaluation_report_errors.append(
                f"namespace_cleanup:{cleanup_error}:index_state_unverified"
            )
        try:
            write_corpus_report(reports_root)
        except Exception as report_exc:
            evaluation_report_errors.append(f"corpus:{type(report_exc).__name__}")
        with create_session() as session:
            release = session.get(RagIndexRelease, release_id)
            if release is not None:
                release.status = "building"
                release.build_status = "failed"
                failed_ids = list(getattr(exc, "failed_item_ids", ()))
                release.build_summary = {
                    **statistics,
                    "expected_vector_count": len(expected_metadata),
                    "verified_vector_count": 0,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "error": type(exc).__name__,
                    "failed_item_count": len(failed_ids),
                    "failed_item_ids": failed_ids[:100],
                    "cleanup_error": cleanup_error,
                    "ingestion_evaluation_report_errors": evaluation_report_errors,
                }
                session.commit()
        raise


def _version_is_eligible(
    version: DocumentVersion,
    *,
    historical: bool,
) -> bool:
    return bool(
        version.publication_status == "published"
        and version.source_verification_status == "verified"
        and version.legal_review_status == "verified"
        and version.ingestion_status == "completed"
        and is_canonical_official_source_url(version.source_url)
        and (historical or version.legal_status in {"active", "amended"})
    )


def _build_is_eligible(
    build: IngestionBuild | None,
    version: DocumentVersion,
) -> bool:
    if build is None:
        return False
    gates = (build.quality_report or {}).get("gates") or {}
    return bool(
        build.version_id == version.version_id
        and build.source_sha256 == version.sha256
        and build.status == "completed"
        and build.review_status == "approved"
        and build.embedding_model == settings.embedding_model
        and build.embedding_revision == settings.embedding_model_revision
        and (build.quality_report or {}).get("status") == "passed"
        and gates
        and all(bool(value) for value in gates.values())
    )


def _release_versions(session, release: RagIndexRelease) -> list[DocumentVersion]:
    rows: list[DocumentVersion] = []
    for document_id, version in release.document_versions.items():
        row = (
            session.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version == int(version),
            )
            .one()
        )
        if row.legal_status not in {"active", "amended"}:
            raise RuntimeError(f"Current release snapshot is stale: {row.version_id}.")
        rows.append(row)
    for version_id in release.historical_version_ids:
        row = session.get(DocumentVersion, version_id)
        if row is None:
            raise RuntimeError(f"Historical version was not found: {version_id}.")
        rows.append(row)
    return rows


def _load_embedded_chunks(
    storage_root: Path,
    document_id: str,
    version: int,
    build_id: str,
) -> list[EmbeddedChunk]:
    base = (
        storage_root
        / "documents"
        / document_id
        / f"v{version}"
        / "builds"
        / build_id
        / "processed"
    )
    chunks_payload = load_json(base / "chunks.json")
    chunk_ids = [str(row.get("chunk_id", "")) for row in chunks_payload]
    if any(not chunk_id for chunk_id in chunk_ids) or len(chunk_ids) != len(
        set(chunk_ids)
    ):
        raise VectorIndexingError(
            "Chunk artifact contains missing or duplicate chunk IDs",
            failed_item_ids=chunk_ids,
        )
    embedding_rows = load_json(base / "embeddings.json")
    embedding_ids = [str(row.get("chunk_id", "")) for row in embedding_rows]
    if any(not chunk_id for chunk_id in embedding_ids) or len(embedding_ids) != len(
        set(embedding_ids)
    ):
        raise VectorIndexingError(
            "Embedding artifact contains missing or duplicate chunk IDs",
            failed_item_ids=embedding_ids,
        )
    if set(chunk_ids) != set(embedding_ids):
        mismatched = sorted(set(chunk_ids).symmetric_difference(embedding_ids))
        raise VectorIndexingError(
            "Chunk and embedding artifacts do not contain the same IDs",
            failed_item_ids=mismatched,
        )
    embedding_payload = {row["chunk_id"]: row for row in embedding_rows}
    result: list[EmbeddedChunk] = []
    for payload in chunks_payload:
        chunk = Chunk(**payload)
        embedded = embedding_payload.get(chunk.chunk_id)
        if embedded is None:
            raise RuntimeError(f"Missing embedding for {chunk.chunk_id}.")
        sparse = embedded.get("sparse_embedding") or {}
        result.append(
            EmbeddedChunk(
                chunk=chunk,
                embedding_model=embedded["embedding_model"],
                embedding=[float(value) for value in embedded["embedding"]],
                sparse_embedding={
                    int(index): float(value) for index, value in sparse.items()
                },
                embedding_revision=str(
                    embedded.get("embedding_revision", "unversioned")
                ),
                retrieval_text_sha256=embedded.get("retrieval_text_sha256"),
            )
        )
    return result


def _validate_artifact_provenance(
    storage_root: Path,
    version: DocumentVersion,
    build: IngestionBuild,
) -> None:
    base = (
        storage_root
        / "documents"
        / version.document_id
        / f"v{version.version}"
        / "builds"
        / build.build_id
    )
    metadata = load_json(base / "metadata" / "document.json")
    validation = load_json(base / "metadata" / "validation.json")
    build_manifest = load_json(base / "metadata" / "build_manifest.json")
    if metadata.get("document_id") != version.document_id:
        raise RuntimeError(f"Artifact document ID mismatch for {version.version_id}.")
    if validation.get("sha256") != version.sha256:
        raise RuntimeError(f"Artifact checksum mismatch for {version.version_id}.")
    if (
        build_manifest.get("build_id") != build.build_id
        or build_manifest.get("config_hash") != build.config_hash
        or build_manifest.get("source_sha256") != version.sha256
    ):
        raise RuntimeError(
            f"Build manifest provenance mismatch for {version.version_id}."
        )
    root = storage_root.resolve()
    for name, expected in (build.artifact_manifest or {}).items():
        path = Path(str(expected.get("path", ""))).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise RuntimeError(f"Build artifact is unavailable: {name}.")
        if _file_manifest(path) != expected:
            raise RuntimeError(f"Build artifact checksum mismatch: {name}.")


def _file_manifest(path: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return {"path": path.as_posix(), "sha256": digest.hexdigest(), "size_bytes": size}
