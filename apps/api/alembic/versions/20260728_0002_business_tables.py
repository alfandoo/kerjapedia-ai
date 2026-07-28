"""create user and business tables

Revision ID: 20260728_0002
Revises: 20260714_0001
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0002"
down_revision: str | None = "20260714_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
        sa.UniqueConstraint("email", name=op.f("uq_user_profiles_email")),
    )
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=True),
        sa.Column("guest_id", sa.String(length=80), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_profiles.user_id"],
            name=op.f("fk_conversations_user_id_user_profiles"),
        ),
        sa.PrimaryKeyConstraint("conversation_id", name=op.f("pk_conversations")),
    )
    op.create_table(
        "document_admin",
        sa.Column("document_id", sa.String(length=80), nullable=False),
        sa.Column("publication_status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("relationships", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("versions_history", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_document_admin")),
    )
    op.create_table(
        "evaluation_datasets",
        sa.Column("dataset_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("dataset_id", name=op.f("pk_evaluation_datasets")),
    )
    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_id", sa.String(length=120), nullable=True),
        sa.Column("rating", sa.String(length=20), nullable=False),
        sa.Column("issue_category", sa.String(length=80), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("feedback_id", name=op.f("pk_feedback")),
    )
    op.create_table(
        "messages",
        sa.Column("message_id", sa.String(length=120), nullable=False),
        sa.Column("conversation_id", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversation_id"],
            name=op.f("fk_messages_conversation_id_conversations"),
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_messages")),
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("run_id", sa.String(length=120), nullable=False),
        sa.Column("dataset_id", sa.String(length=120), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["evaluation_datasets.dataset_id"],
            name=op.f("fk_evaluation_runs_dataset_id_evaluation_datasets"),
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_evaluation_runs")),
    )
    op.create_table(
        "uploaded_documents",
        sa.Column("upload_id", sa.String(length=120), nullable=False),
        sa.Column("document_id", sa.String(length=80), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("upload_id", name=op.f("pk_uploaded_documents")),
    )


def downgrade() -> None:
    op.drop_table("uploaded_documents")
    op.drop_table("evaluation_runs")
    op.drop_table("messages")
    op.drop_table("feedback")
    op.drop_table("evaluation_datasets")
    op.drop_table("document_admin")
    op.drop_table("conversations")
    op.drop_table("user_profiles")
