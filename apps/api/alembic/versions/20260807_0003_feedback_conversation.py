"""add conversation_id to feedback

Revision ID: 20260807_0003
Revises: 20260728_0002
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0003"
down_revision: str | None = "20260728_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "feedback",
        sa.Column("conversation_id", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feedback", "conversation_id")
