"""persist RAG observability observations across restarts

Revision ID: 20260916_0013
Revises: 20260916_0012
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260916_0013"
down_revision: str | None = "20260916_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_request_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("request_latency_ms", sa.Float(), nullable=True),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("llm_model", sa.String(160), nullable=True),
        sa.Column("claims_supported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claims_unsupported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topic", sa.String(120), nullable=False, server_default="unknown"),
        sa.Column("is_followup", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("stage_latencies", sa.JSONB(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_request_observations_created_at", "rag_request_observations", ["created_at"]
    )
    op.create_table(
        "rag_provider_errors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_provider_errors_created_at", "rag_provider_errors", ["created_at"]
    )
    op.create_table(
        "rag_ragas_evals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_ragas_evals_created_at", "rag_ragas_evals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_ragas_evals_created_at", table_name="rag_ragas_evals")
    op.drop_table("rag_ragas_evals")
    op.drop_index("ix_rag_provider_errors_created_at", table_name="rag_provider_errors")
    op.drop_table("rag_provider_errors")
    op.drop_index(
        "ix_rag_request_observations_created_at", table_name="rag_request_observations"
    )
    op.drop_table("rag_request_observations")
