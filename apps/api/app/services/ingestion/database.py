from __future__ import annotations

import math
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.ingestion import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionBuild,
    IngestionJob,
)
from app.services.ingestion.builds import (
    IngestionBuildConfig,
    document_metadata_hash,
    make_build_identity,
)
from app.services.ingestion.domain import content_sha256
from app.services.ingestion.governance import is_canonical_official_source_url
from app.services.ingestion.provenance import build_legacy_chunk_provenance
from app.services.ingestion.quality import text_sha256
from app.services.ingestion.schemas import (
    DocumentMetadata,
    EmbeddedChunk,
    IngestionResult,
)


def persist_ingestion_result(
    session: Session,
    document: DocumentMetadata,
    result: IngestionResult,
    embedded_chunks: list[EmbeddedChunk],
    *,
    build_config: IngestionBuildConfig,
    job_id: str | None = None,
) -> str:
    """Atomically store a prepared build or reuse its verified materialization."""
    try:
        disposition = _persist_ingestion_result(
            session,
            document,
            result,
            embedded_chunks,
            build_config=build_config,
            job_id=job_id,
        )
        session.commit()
        return disposition
    except Exception:
        session.rollback()
        raise


def _persist_ingestion_result(
    session: Session,
    document: DocumentMetadata,
    result: IngestionResult,
    embedded_chunks: list[EmbeddedChunk],
    *,
    build_config: IngestionBuildConfig,
    job_id: str | None = None,
) -> str:
    if not result.build_id or not result.config_hash:
        raise ValueError("Immutable ingestion persistence requires build provenance.")
    identity = make_build_identity(
        document.document_id,
        document.sha256,
        build_config,
        document_metadata_hash(document),
    )
    if (
        result.build_id != identity.build_id
        or result.config_hash != identity.config_hash
    ):
        raise RuntimeError("Prepared ingestion result has a stale build identity.")

    chunk_ids = [item.chunk.chunk_id for item in embedded_chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Chunk IDs must be unique within an ingestion build.")
    wrong_document_ids = sorted(
        {
            item.chunk.document_id
            for item in embedded_chunks
            if item.chunk.document_id != document.document_id
        }
    )
    if wrong_document_ids:
        raise ValueError(
            "Chunks belong to a different document: " + ", ".join(wrong_document_ids)
        )

    calculated_version_id = f"{document.document_id}-v{result.version}"
    version_row = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.sha256 == document.sha256)
        .one_or_none()
    )
    if version_row is not None and version_row.document_id != document.document_id:
        raise RuntimeError(
            "Source file is already registered to another document; no duplicate "
            "document version was created."
        )
    if version_row is None:
        collision = session.get(DocumentVersion, calculated_version_id)
        if collision is not None and collision.sha256 != document.sha256:
            raise RuntimeError(
                "Document version identity collision; no existing version was modified."
            )
        version_id = calculated_version_id
    else:
        version_id = version_row.version_id

    existing_build = session.get(IngestionBuild, result.build_id)
    if existing_build is not None and existing_build.status in {
        "completed",
        "review_required",
    }:
        _verify_reusable_build(
            session,
            existing_build,
            version_id=version_id,
            document=document,
            result=result,
            embedded_chunks=embedded_chunks,
            identity_metadata_hash=identity.metadata_hash,
        )
        _mark_job_reused(
            session,
            job_id or f"ing_{result.build_id}",
            existing_build,
            result,
        )
        return "reused"

    session.merge(
        Document(
            document_id=document.document_id,
            title=document.title,
            short_title=document.short_title,
            regulation_type=document.regulation_type,
            number=document.number,
            year=document.year,
            issuer=document.issuer,
            topics=document.topics,
        )
    )
    if version_row is None:
        version_row = DocumentVersion(
            version_id=version_id,
            document_id=document.document_id,
            version=result.version,
            sha256=document.sha256,
            size_bytes=document.size_bytes,
            local_file=document.local_file,
            source_url=document.source_url,
            legal_status=document.legal_status,
            verification_status=document.verification_status,
            source_verification_status=(
                "verified"
                if (
                    document.verification_status == "verified"
                    and is_canonical_official_source_url(document.source_url)
                )
                else "pending"
            ),
            legal_review_status="pending",
            publication_status="draft",
            ingestion_status=result.status,
            is_current=False,
            artifact_paths={},
        )
        session.add(version_row)
    else:
        if version_row.sha256 != document.sha256:
            raise RuntimeError(f"Document version checksum changed for {version_id}.")
        version_row.size_bytes = document.size_bytes
        version_row.local_file = document.local_file
        version_row.source_url = document.source_url
    session.flush()

    build = session.get(IngestionBuild, result.build_id)
    if build is None:
        build = IngestionBuild(
            build_id=result.build_id,
            version_id=version_id,
            document_id=document.document_id,
            source_sha256=document.sha256,
            metadata_hash=identity.metadata_hash,
            pipeline_version=build_config.pipeline_version,
            config_hash=result.config_hash,
            pipeline_config=build_config.payload(),
            parser_version=build_config.parser_version,
            chunker_version=build_config.chunker_version,
            ocr_engine=build_config.ocr_profile,
            embedding_model=build_config.embedding_model,
            embedding_revision=build_config.embedding_revision,
            status=result.status,
            review_status="pending",
            quality_report=result.quality_report,
            artifact_manifest=result.artifact_manifest,
            page_dispositions={},
            reviewed_by=None,
            reviewed_at=None,
            review_notes="",
            completed_at=datetime.now(UTC),
        )
        session.add(build)
    else:
        if (
            build.version_id != version_id
            or build.source_sha256 != document.sha256
            or build.config_hash != result.config_hash
            or build.metadata_hash != identity.metadata_hash
        ):
            raise RuntimeError(
                f"Ingestion build provenance conflict: {result.build_id}."
            )
        build.status = result.status
        build.quality_report = result.quality_report
        build.artifact_manifest = result.artifact_manifest
        build.completed_at = datetime.now(UTC)

    paths = dict(version_row.artifact_paths or {})
    builds = dict(paths.get("builds", {}))
    builds[result.build_id] = result.artifacts
    paths["builds"] = builds
    paths["latest_build_id"] = result.build_id
    version_row.artifact_paths = paths
    if not version_row.is_current and (
        result.status == "completed" or version_row.ingestion_status != "completed"
    ):
        version_row.ingestion_status = result.status
    session.flush()

    existing_chunk_created_at = dict(
        session.query(DocumentChunk.chunk_id, DocumentChunk.created_at)
        .filter(DocumentChunk.build_id == result.build_id)
        .all()
    )
    chunk_rows: list[DocumentChunk] = []
    embedding_rows: list[ChunkEmbedding] = []
    persisted_at = datetime.now(UTC)
    for chunk_index, embedded_chunk in enumerate(embedded_chunks):
        chunk = embedded_chunk.chunk
        retrieval_text = chunk.retrieval_text or chunk.text
        created_at = existing_chunk_created_at.get(chunk.chunk_id) or persisted_at
        provenance = build_legacy_chunk_provenance(
            document,
            chunk,
            chunk_index=chunk_index,
            ingestion_version=f"v{result.version}",
            parser_version=build_config.parser_version,
            chunker_version=build_config.chunker_version,
            embedding_model=embedded_chunk.embedding_model,
            created_at=created_at,
            updated_at=persisted_at,
        )
        structure = provenance["structure"]
        chunk_metadata = provenance["chunk"]
        chunk_rows.append(
            DocumentChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                version_id=version_id,
                build_id=result.build_id,
                chapter=chunk.chapter,
                section=chunk.section,
                article=chunk.article,
                paragraph=chunk.paragraph,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                token_count=chunk.token_count,
                text=chunk.text,
                retrieval_text=retrieval_text,
                chunk_type=chunk.chunk_type,
                artifact_checksum=chunk.artifact_checksum,
                parent_chunk_id=chunk_metadata["parent_chunk_id"],
                chunk_index=chunk_metadata["chunk_index"],
                legal_node_id=structure["legal_node_id"],
                section_path=structure["section_path"],
                content_hash=chunk_metadata["content_hash"],
                metadata_hash=chunk_metadata["metadata_hash"],
                provenance=provenance,
                payload={**asdict(chunk), "provenance": provenance},
                created_at=created_at,
                updated_at=persisted_at,
            )
        )
        vector_norm = math.sqrt(
            sum(float(value) * float(value) for value in embedded_chunk.embedding)
        )
        embedding_rows.append(
            ChunkEmbedding(
                chunk_id=chunk.chunk_id,
                build_id=result.build_id,
                embedding_model=embedded_chunk.embedding_model,
                embedding_revision=embedded_chunk.embedding_revision,
                dimensions=len(embedded_chunk.embedding),
                vector_norm=vector_norm,
                embedding=embedded_chunk.embedding,
                sparse_embedding={
                    str(index): float(value)
                    for index, value in (embedded_chunk.sparse_embedding or {}).items()
                },
                retrieval_text_sha256=(
                    embedded_chunk.retrieval_text_sha256 or text_sha256(retrieval_text)
                ),
            )
        )
    # Build and validate all replacement rows before deleting the prior build.
    session.execute(
        delete(ChunkEmbedding).where(ChunkEmbedding.build_id == result.build_id)
    )
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.build_id == result.build_id)
    )
    session.add_all(chunk_rows)
    session.flush()
    session.add_all(embedding_rows)
    session.flush()
    _verify_reusable_build(
        session,
        build,
        version_id=version_id,
        document=document,
        result=result,
        embedded_chunks=embedded_chunks,
        identity_metadata_hash=identity.metadata_hash,
    )

    resolved_job_id = job_id or f"ing_{result.build_id}"
    job = session.get(IngestionJob, resolved_job_id)
    if job is None:
        job = IngestionJob(
            job_id=resolved_job_id,
            document_id=document.document_id,
            version_id=version_id,
            build_id=result.build_id,
            status=result.status,
            warnings=result.warnings,
            artifact_paths=result.artifacts,
        )
        session.add(job)
    else:
        job.version_id = version_id
        job.build_id = result.build_id
        job.status = result.status
        job.warnings = result.warnings
        job.artifact_paths = result.artifacts
    return "stored"


def _verify_reusable_build(
    session: Session,
    build: IngestionBuild,
    *,
    version_id: str,
    document: DocumentMetadata,
    result: IngestionResult,
    embedded_chunks: list[EmbeddedChunk],
    identity_metadata_hash: str,
) -> None:
    conflicts: list[str] = []
    if build.version_id != version_id or build.source_sha256 != document.sha256:
        conflicts.append("source identity")
    if build.config_hash != result.config_hash:
        conflicts.append("pipeline configuration")
    if build.metadata_hash != identity_metadata_hash:
        conflicts.append("document metadata")
    if build.status != result.status:
        conflicts.append("terminal status")
    if build.artifact_manifest != result.artifact_manifest:
        conflicts.append("artifact manifest")

    stored_chunks = (
        session.query(DocumentChunk)
        .filter(DocumentChunk.build_id == build.build_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    expected_chunks = [
        (item.chunk.chunk_id, index, content_sha256(item.chunk.text))
        for index, item in enumerate(embedded_chunks)
    ]
    actual_chunks = [
        (row.chunk_id, row.chunk_index, row.content_hash) for row in stored_chunks
    ]
    if actual_chunks != expected_chunks:
        conflicts.append("chunk materialization")

    stored_embeddings = {
        row.chunk_id: row
        for row in session.query(ChunkEmbedding)
        .filter(ChunkEmbedding.build_id == build.build_id)
        .all()
    }
    if set(stored_embeddings) != {item.chunk.chunk_id for item in embedded_chunks}:
        conflicts.append("embedding membership")
    else:
        for item in embedded_chunks:
            row = stored_embeddings[item.chunk.chunk_id]
            retrieval_text = item.chunk.retrieval_text or item.chunk.text
            expected_input_hash = item.retrieval_text_sha256 or text_sha256(
                retrieval_text
            )
            if (
                row.embedding_model != item.embedding_model
                or row.embedding_revision != item.embedding_revision
                or row.dimensions != len(item.embedding)
                or row.retrieval_text_sha256 != expected_input_hash
            ):
                conflicts.append("embedding materialization")
                break

    if conflicts:
        raise RuntimeError(
            "Completed ingestion build is immutable and conflicts with the prepared "
            "result: " + ", ".join(sorted(set(conflicts)))
        )


def _mark_job_reused(
    session: Session,
    job_id: str,
    build: IngestionBuild,
    result: IngestionResult,
) -> None:
    job = session.get(IngestionJob, job_id)
    if job is None:
        return
    job.version_id = build.version_id
    job.build_id = build.build_id
    job.status = build.status
    job.warnings = result.warnings
    job.artifact_paths = result.artifacts
