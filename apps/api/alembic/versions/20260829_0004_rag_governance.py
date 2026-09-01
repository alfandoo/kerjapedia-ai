"""add high-assurance RAG governance

Revision ID: 20260829_0004
Revises: 20260807_0003
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260829_0004"
down_revision: str | None = "20260807_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column(
            "source_verification_status", sa.String(40), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column("legal_review_status", sa.String(40), nullable=False, server_default="pending"),
    )
    op.add_column(
        "document_versions",
        sa.Column("publication_status", sa.String(20), nullable=False, server_default="draft"),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "ingestion_status",
            sa.String(40),
            nullable=False,
            server_default="review_required",
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("document_versions", sa.Column("verified_by", sa.String(160)))
    op.add_column("document_versions", sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.add_column("document_versions", sa.Column("valid_from", sa.DateTime(timezone=True)))
    op.add_column("document_versions", sa.Column("valid_to", sa.DateTime(timezone=True)))
    op.create_unique_constraint(
        "uq_document_version_number",
        "document_versions",
        ["document_id", "version"],
    )
    op.create_check_constraint(
        "ck_document_version_source_verification",
        "document_versions",
        "source_verification_status IN ('pending', 'verified', 'rejected')",
    )
    op.create_check_constraint(
        "ck_document_version_legal_review",
        "document_versions",
        "legal_review_status IN ('pending', 'verified', 'rejected')",
    )
    op.create_check_constraint(
        "ck_document_version_publication",
        "document_versions",
        "publication_status IN ('draft', 'published', 'retired')",
    )
    op.create_check_constraint(
        "ck_document_version_ingestion_status",
        "document_versions",
        "ingestion_status IN ('queued', 'running', 'completed', 'review_required', 'failed')",
    )
    op.create_index(
        "ix_document_version_retrieval_eligibility",
        "document_versions",
        [
            "is_current",
            "publication_status",
            "ingestion_status",
            "source_verification_status",
            "legal_review_status",
        ],
    )
    op.execute(
        "UPDATE document_versions SET source_verification_status = "
        "CASE WHEN verification_status = 'verified' THEN 'verified' ELSE 'pending' END"
    )
    op.execute(
        "UPDATE document_versions dv SET ingestion_status = COALESCE(("
        "SELECT ij.status FROM ingestion_jobs ij WHERE ij.version_id = dv.version_id "
        "ORDER BY ij.created_at DESC NULLS LAST LIMIT 1), 'review_required')"
    )
    op.execute(
        "WITH ranked AS (SELECT version_id, ROW_NUMBER() OVER ("
        "PARTITION BY document_id ORDER BY created_at DESC NULLS LAST, version DESC, "
        "version_id DESC) AS row_number FROM document_versions) "
        "UPDATE document_versions dv SET is_current = (ranked.row_number = 1) "
        "FROM ranked WHERE ranked.version_id = dv.version_id"
    )
    op.create_index(
        "uq_document_version_single_current",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "document_relationships",
        sa.Column("relationship_id", sa.String(160), primary_key=True),
        sa.Column(
            "from_document_id",
            sa.String(80),
            sa.ForeignKey("documents.document_id"),
            nullable=False,
        ),
        sa.Column(
            "to_document_id", sa.String(80), sa.ForeignKey("documents.document_id"), nullable=False
        ),
        sa.Column("relationship_type", sa.String(40), nullable=False),
        sa.Column("from_article", sa.String(80)),
        sa.Column("to_article", sa.String(80)),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("evidence_url", sa.Text()),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(160)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "relationship_type IN ('amended_by', 'revoked_by', 'replaced_by', "
            "'implements', 'implemented_by', 'related_to')",
            name="ck_document_relationship_type",
        ),
    )
    op.create_table(
        "document_verification_audits",
        sa.Column("audit_id", sa.String(160), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(120),
            sa.ForeignKey("document_versions.version_id"),
            nullable=False,
        ),
        sa.Column("verification_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reviewer", sa.String(160), nullable=False),
        sa.Column("evidence_url", sa.Text()),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "rag_index_releases",
        sa.Column("release_id", sa.String(160), primary_key=True),
        sa.Column("namespace", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("build_status", sa.String(20), nullable=False),
        sa.Column("embedding_model", sa.String(160), nullable=False),
        sa.Column("reranker_model", sa.String(160), nullable=False),
        sa.Column("generator_model", sa.String(160), nullable=False),
        sa.Column("verifier_model", sa.String(160), nullable=False),
        sa.Column("prompt_version_id", sa.String(160), nullable=False),
        sa.Column("relationship_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("document_versions", postgresql.JSONB(), nullable=False),
        sa.Column("historical_version_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evaluation_metrics", postgresql.JSONB(), nullable=False),
        sa.Column("retrieval_thresholds", postgresql.JSONB(), nullable=False),
        sa.Column("build_summary", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('building', 'validated', 'active', 'retired')",
            name="ck_rag_index_release_status",
        ),
        sa.CheckConstraint(
            "build_status IN ('pending', 'queued', 'running', 'succeeded', 'failed')",
            name="ck_rag_index_release_build_status",
        ),
    )
    op.create_index(
        "uq_rag_index_release_single_active",
        "rag_index_releases",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "release_id",
            sa.String(160),
            sa.ForeignKey("rag_index_releases.release_id"),
        ),
    )
    op.create_table(
        "evaluation_question_reviews",
        sa.Column("review_id", sa.String(160), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(120),
            sa.ForeignKey("evaluation_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("question_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reviewer", sa.String(160), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('verified', 'rejected')",
            name="ck_evaluation_question_review_status",
        ),
    )
    op.create_index(
        "ix_evaluation_question_review_latest",
        "evaluation_question_reviews",
        ["dataset_id", "question_id", "reviewed_at", "review_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_question_review_latest",
        table_name="evaluation_question_reviews",
    )
    op.drop_table("evaluation_question_reviews")
    op.drop_column("evaluation_runs", "release_id")
    op.drop_index("uq_rag_index_release_single_active", table_name="rag_index_releases")
    op.drop_table("rag_index_releases")
    op.drop_table("document_verification_audits")
    op.drop_table("document_relationships")
    op.drop_index(
        "uq_document_version_single_current",
        table_name="document_versions",
    )
    op.drop_index(
        "ix_document_version_retrieval_eligibility",
        table_name="document_versions",
    )
    op.drop_constraint(
        "ck_document_version_ingestion_status",
        "document_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_document_version_publication",
        "document_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_document_version_legal_review",
        "document_versions",
        type_="check",
    )
    op.drop_constraint(
        "ck_document_version_source_verification",
        "document_versions",
        type_="check",
    )
    op.drop_constraint(
        "uq_document_version_number",
        "document_versions",
        type_="unique",
    )
    for column in (
        "valid_to",
        "valid_from",
        "verified_at",
        "verified_by",
        "is_current",
        "ingestion_status",
        "publication_status",
        "legal_review_status",
        "source_verification_status",
    ):
        op.drop_column("document_versions", column)
