"""track async evaluation run status and progress

Revision ID: 20260916_0012
Revises: 20260914_0011
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260916_0012"
down_revision: str | None = "20260914_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("progress_completed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("evaluation_runs", sa.Column("error", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE evaluation_runs
        SET status = 'completed'
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "error")
    op.drop_column("evaluation_runs", "progress_total")
    op.drop_column("evaluation_runs", "progress_completed")
    op.drop_column("evaluation_runs", "status")
