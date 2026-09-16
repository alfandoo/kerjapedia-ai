from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    short_title: Mapped[str] = mapped_column(String(120), nullable=False)
    regulation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_version_number"),
        UniqueConstraint(
            "sha256",
            name="uq_document_versions_source_sha256",
        ),
        CheckConstraint(
            "source_verification_status IN ('pending', 'verified', 'rejected')",
            name="ck_document_version_source_verification",
        ),
        CheckConstraint(
            "legal_review_status IN ('pending', 'verified', 'rejected')",
            name="ck_document_version_legal_review",
        ),
        CheckConstraint(
            "publication_status IN ('draft', 'published', 'retired')",
            name="ck_document_version_publication",
        ),
        CheckConstraint(
            "ingestion_status IN ('queued', 'running', 'completed', 'review_required', 'failed')",
            name="ck_document_version_ingestion_status",
        ),
        Index(
            "ix_document_version_retrieval_eligibility",
            "is_current",
            "publication_status",
            "ingestion_status",
            "source_verification_status",
            "legal_review_status",
        ),
        Index(
            "uq_document_version_single_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    version_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.document_id"), nullable=False
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    local_file: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    legal_status: Mapped[str] = mapped_column(String(80), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(80), nullable=False)
    source_verification_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pending"
    )
    legal_review_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pending"
    )
    publication_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )
    ingestion_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="review_required"
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by: Mapped[str | None] = mapped_column(String(160))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    artifact_paths: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class IngestionBuild(Base):
    __tablename__ = "ingestion_builds"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "config_hash",
            "metadata_hash",
            "embedding_model",
            "embedding_revision",
            name="uq_ingestion_build_fingerprint",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'review_required', 'failed')",
            name="ck_ingestion_build_status",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="ck_ingestion_build_review_status",
        ),
        Index("ix_ingestion_build_version_status", "version_id", "status"),
        Index("ix_ingestion_build_document_created", "document_id", "created_at"),
    )

    build_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.version_id"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.document_id"), nullable=False
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(80), nullable=False)
    ocr_engine: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    quality_report: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    artifact_manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    page_dispositions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentChunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            "page_start > 0 AND page_end >= page_start",
            name="ck_chunks_page_range",
        ),
        UniqueConstraint(
            "build_id",
            "chunk_index",
            name="uq_chunks_build_chunk_index",
        ),
        Index("ix_chunks_build_id", "build_id"),
        Index("ix_chunks_content_hash", "content_hash"),
    )

    chunk_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.document_id"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.version_id"),
        nullable=False,
    )
    build_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_builds.build_id")
    )
    chapter: Mapped[str | None] = mapped_column(String(80))
    section: Mapped[str | None] = mapped_column(String(160))
    article: Mapped[str | None] = mapped_column(String(80))
    paragraph: Mapped[str | None] = mapped_column(String(80))
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_text: Mapped[str | None] = mapped_column(Text)
    chunk_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="substantive"
    )
    artifact_checksum: Mapped[str | None] = mapped_column(String(64))
    parent_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("chunks.chunk_id", ondelete="RESTRICT")
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    legal_node_id: Mapped[str | None] = mapped_column(String(200))
    section_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (Index("ix_chunk_embeddings_build_id", "build_id"),)

    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("chunks.chunk_id"), primary_key=True
    )
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    # External embedding imports keep the immutable vector payload in its
    # accepted artifact and Pinecone.  The relational row records provenance
    # without duplicating 1,024 floats per chunk.
    embedding: Mapped[list[float] | None] = mapped_column(JSONB)
    build_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_builds.build_id")
    )
    embedding_revision: Mapped[str | None] = mapped_column(String(160))
    dimensions: Mapped[int | None] = mapped_column(Integer)
    vector_norm: Mapped[float | None] = mapped_column(Float)
    sparse_embedding: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    retrieval_text_sha256: Mapped[str | None] = mapped_column(String(64))
    embedding_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    import_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="generated"
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_build_id", "build_id"),)

    job_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.document_id"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.version_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    artifact_paths: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    build_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_builds.build_id")
    )


class DocumentRelationship(Base):
    __tablename__ = "document_relationships"

    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('amended_by', 'revoked_by', 'replaced_by', "
            "'implements', 'implemented_by', 'related_to')",
            name="ck_document_relationship_type",
        ),
    )

    relationship_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    from_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.document_id"), nullable=False
    )
    to_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.document_id"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_article: Mapped[str | None] = mapped_column(String(80))
    to_article: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    evidence_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVerificationAudit(Base):
    __tablename__ = "document_verification_audits"

    audit_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.version_id"), nullable=False
    )
    verification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class RagIndexRelease(Base):
    __tablename__ = "rag_index_releases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('building', 'validated', 'active', 'retired')",
            name="ck_rag_index_release_status",
        ),
        CheckConstraint(
            "build_status IN ('pending', 'queued', 'running', 'succeeded', 'failed')",
            name="ck_rag_index_release_build_status",
        ),
        Index(
            "uq_rag_index_release_single_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    release_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="building")
    build_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False)
    reranker_model: Mapped[str] = mapped_column(String(160), nullable=False)
    generator_model: Mapped[str] = mapped_column(String(160), nullable=False)
    verifier_model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version_id: Mapped[str] = mapped_column(String(160), nullable=False)
    relationship_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_versions: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    historical_version_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    evaluation_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    retrieval_thresholds: Mapped[dict[str, float]] = mapped_column(
        JSONB, nullable=False, default=lambda: {"general": 0.08}
    )
    ingestion_builds: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    build_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
