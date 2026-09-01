"""create ingestion tables

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "documents",
        sa.Column("document_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("short_title", sa.String(length=120), nullable=False),
        sa.Column("regulation_type", sa.String(length=40), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_documents")),
    )
    op.create_table(
        "document_versions",
        sa.Column("version_id", sa.String(length=120), nullable=False),
        sa.Column("document_id", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("local_file", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("legal_status", sa.String(length=80), nullable=False),
        sa.Column("verification_status", sa.String(length=80), nullable=False),
        sa.Column("artifact_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name=op.f("fk_document_versions_document_id_documents"),
        ),
        sa.PrimaryKeyConstraint("version_id", name=op.f("pk_document_versions")),
    )
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.String(length=160), nullable=False),
        sa.Column("document_id", sa.String(length=80), nullable=False),
        sa.Column("version_id", sa.String(length=120), nullable=False),
        sa.Column("chapter", sa.String(length=80), nullable=True),
        sa.Column("section", sa.String(length=160), nullable=True),
        sa.Column("article", sa.String(length=80), nullable=True),
        sa.Column("paragraph", sa.String(length=80), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name=op.f("fk_chunks_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.version_id"],
            name=op.f("fk_chunks_version_id_document_versions"),
        ),
        sa.PrimaryKeyConstraint("chunk_id", name=op.f("pk_chunks")),
    )
    op.create_table(
        "chunk_embeddings",
        sa.Column("chunk_id", sa.String(length=160), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.chunk_id"],
            name=op.f("fk_chunk_embeddings_chunk_id_chunks"),
        ),
        sa.PrimaryKeyConstraint("chunk_id", name=op.f("pk_chunk_embeddings")),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.String(length=160), nullable=False),
        sa.Column("document_id", sa.String(length=80), nullable=False),
        sa.Column("version_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name=op.f("fk_ingestion_jobs_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.version_id"],
            name=op.f("fk_ingestion_jobs_version_id_document_versions"),
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_ingestion_jobs")),
    )


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
    op.drop_table("chunk_embeddings")
    op.drop_table("chunks")
    op.drop_table("document_versions")
    op.drop_table("documents")
