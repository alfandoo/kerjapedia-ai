"""record external embedding provenance without duplicating vectors

Revision ID: 20260914_0011
Revises: 20260913_0010
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260914_0011"
down_revision: str | None = "20260913_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("chunk_embeddings", "embedding", nullable=True)
    op.add_column(
        "chunk_embeddings", sa.Column("embedding_artifact_sha256", sa.String(64))
    )
    op.add_column(
        "chunk_embeddings",
        sa.Column(
            "import_status",
            sa.String(40),
            nullable=False,
            server_default="generated",
        ),
    )
    op.execute(
        """
        UPDATE chunk_embeddings
        SET import_status = 'generated'
        WHERE import_status IS NULL
        """
    )
    op.alter_column("chunk_embeddings", "import_status", server_default=None)


def downgrade() -> None:
    external_rows = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM chunk_embeddings WHERE embedding IS NULL")
    ).scalar_one()
    if external_rows:
        raise RuntimeError(
            "Cannot downgrade while external embedding records omit vector payloads."
        )
    op.drop_column("chunk_embeddings", "import_status")
    op.drop_column("chunk_embeddings", "embedding_artifact_sha256")
    op.alter_column("chunk_embeddings", "embedding", nullable=False)
