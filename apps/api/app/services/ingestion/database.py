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
from app.services.ingestion.builds import IngestionBuildConfig
from app.services.ingestion.governance import is_canonical_official_source_url
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
) -> None:
    if not result.build_id or not result.config_hash:
        raise ValueError("Immutable ingestion persistence requires build provenance.")
    version_id = f"{document.document_id}-v{result.version}"
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
    version_row = session.get(DocumentVersion, version_id)
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

    session.execute(
        delete(ChunkEmbedding).where(ChunkEmbedding.build_id == result.build_id)
    )
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.build_id == result.build_id)
    )
    chunk_rows: list[DocumentChunk] = []
    embedding_rows: list[ChunkEmbedding] = []
    for embedded_chunk in embedded_chunks:
        chunk = embedded_chunk.chunk
        retrieval_text = chunk.retrieval_text or chunk.text
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
                payload=asdict(chunk),
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
    session.add_all(chunk_rows)
    session.add_all(embedding_rows)

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
    session.commit()
