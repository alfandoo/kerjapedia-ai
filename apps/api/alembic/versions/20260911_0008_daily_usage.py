"""add per-identity daily usage metering

Revision ID: 20260911_0008
Revises: 20260902_0007
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260911_0008"
down_revision: str | None = "20260902_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_usage",
        sa.Column("user_key", sa.String(length=160), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "completion_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_key", "usage_date"),
    )
    op.create_index(
        "ix_daily_usage_date", "daily_usage", ["usage_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_daily_usage_date", table_name="daily_usage")
    op.drop_table("daily_usage")
