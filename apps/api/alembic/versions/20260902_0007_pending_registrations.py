"""add pending email registrations for deferred signup

Revision ID: 20260902_0007
Revises: 20260901_0006
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260902_0007"
down_revision: str | None = "20260901_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_registrations",
        sa.Column("email", sa.String(length=320), primary_key=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("otp_hash", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pending_registrations")
