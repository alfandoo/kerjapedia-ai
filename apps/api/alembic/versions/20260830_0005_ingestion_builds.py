"""add immutable technical ingestion builds

Revision ID: 20260830_0005
Revises: 20260829_0004
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_0005"
down_revision: str | None = "20260829_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "document_versions",
        "version",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.create_table(
        "ingestion_builds",
        sa.Column("build_id", sa.String(160), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(120),
            sa.ForeignKey("document_versions.version_id"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(80),
            sa.ForeignKey("documents.document_id"),
            nullable=False,
        ),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(80), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("pipeline_config", postgresql.JSONB(), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("chunker_version", sa.String(80), nullable=False),
        sa.Column("ocr_engine", sa.String(160), nullable=False),
        sa.Column("embedding_model", sa.String(160), nullable=False),
        sa.Column("embedding_revision", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="queued"),
        sa.Column(
            "review_status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column(
            "quality_report",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "artifact_manifest",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "page_dispositions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reviewed_by", sa.String(160)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'review_required', 'failed')",
            name="ck_ingestion_build_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="ck_ingestion_build_review_status",
        ),
        sa.UniqueConstraint(
            "version_id",
            "config_hash",
            "embedding_model",
            "embedding_revision",
            name="uq_ingestion_build_fingerprint",
        ),
    )
    op.create_index(
        "ix_ingestion_build_version_status",
        "ingestion_builds",
        ["version_id", "status"],
    )
    op.create_index(
        "ix_ingestion_build_document_created",
        "ingestion_builds",
        ["document_id", "created_at"],
    )

    op.add_column(
        "chunks",
        sa.Column(
            "build_id", sa.String(160), sa.ForeignKey("ingestion_builds.build_id")
        ),
    )
    op.add_column("chunks", sa.Column("retrieval_text", sa.Text()))
    op.add_column(
        "chunks",
        sa.Column(
            "chunk_type", sa.String(40), nullable=False, server_default="substantive"
        ),
    )
    op.add_column("chunks", sa.Column("artifact_checksum", sa.String(64)))
    op.create_index("ix_chunks_build_id", "chunks", ["build_id"])

    op.add_column(
        "chunk_embeddings",
        sa.Column(
            "build_id", sa.String(160), sa.ForeignKey("ingestion_builds.build_id")
        ),
    )
    op.add_column("chunk_embeddings", sa.Column("embedding_revision", sa.String(160)))
    op.add_column("chunk_embeddings", sa.Column("dimensions", sa.Integer()))
    op.add_column("chunk_embeddings", sa.Column("vector_norm", sa.Float()))
    op.add_column("chunk_embeddings", sa.Column("sparse_embedding", postgresql.JSONB()))
    op.add_column("chunk_embeddings", sa.Column("retrieval_text_sha256", sa.String(64)))
    op.create_index("ix_chunk_embeddings_build_id", "chunk_embeddings", ["build_id"])

    op.add_column(
        "ingestion_jobs",
        sa.Column(
            "build_id", sa.String(160), sa.ForeignKey("ingestion_builds.build_id")
        ),
    )
    op.create_index("ix_ingestion_jobs_build_id", "ingestion_jobs", ["build_id"])
    op.add_column(
        "rag_index_releases",
        sa.Column(
            "ingestion_builds",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("rag_index_releases", "ingestion_builds")
    op.drop_index("ix_ingestion_jobs_build_id", table_name="ingestion_jobs")
    op.drop_column("ingestion_jobs", "build_id")
    op.drop_index("ix_chunk_embeddings_build_id", table_name="chunk_embeddings")
    for column in (
        "retrieval_text_sha256",
        "sparse_embedding",
        "vector_norm",
        "dimensions",
        "embedding_revision",
        "build_id",
    ):
        op.drop_column("chunk_embeddings", column)
    op.drop_index("ix_chunks_build_id", table_name="chunks")
    for column in ("artifact_checksum", "chunk_type", "retrieval_text", "build_id"):
        op.drop_column("chunks", column)
    op.drop_index("ix_ingestion_build_document_created", table_name="ingestion_builds")
    op.drop_index("ix_ingestion_build_version_status", table_name="ingestion_builds")
    op.drop_table("ingestion_builds")
    op.alter_column(
        "document_versions",
        "version",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
