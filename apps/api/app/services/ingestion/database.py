from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.models.ingestion import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
)
from app.services.ingestion.schemas import DocumentMetadata, EmbeddedChunk, IngestionResult


def persist_ingestion_result(
    session: Session,
    document: DocumentMetadata,
    result: IngestionResult,
    embedded_chunks: list[EmbeddedChunk],
) -> None:
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
    session.merge(
        DocumentVersion(
            version_id=version_id,
            document_id=document.document_id,
            version=result.version,
            sha256=document.sha256,
            size_bytes=document.size_bytes,
            local_file=document.local_file,
            source_url=document.source_url,
            legal_status=document.legal_status,
            verification_status=document.verification_status,
            artifact_paths=result.artifacts,
        )
    )

    for embedded_chunk in embedded_chunks:
        chunk = embedded_chunk.chunk
        session.merge(
            DocumentChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                version_id=version_id,
                chapter=chunk.chapter,
                section=chunk.section,
                article=chunk.article,
                paragraph=chunk.paragraph,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                token_count=chunk.token_count,
                text=chunk.text,
                payload=asdict(chunk),
            )
        )
        session.merge(
            ChunkEmbedding(
                chunk_id=chunk.chunk_id,
                embedding_model=embedded_chunk.embedding_model,
                embedding=embedded_chunk.embedding,
            )
        )

    session.merge(
        IngestionJob(
            job_id=f"{document.document_id}-v{result.version}",
            document_id=document.document_id,
            version_id=version_id,
            status=result.status,
            warnings=result.warnings,
            artifact_paths=result.artifacts,
        )
    )
    session.commit()
