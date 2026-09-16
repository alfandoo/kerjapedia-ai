"""store observability stage latencies as jsonb like the rest of the schema

Revision ID: 20260916_0014
Revises: 20260916_0013
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260916_0014"
down_revision: str | None = "20260916_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE rag_request_observations"
        " ALTER COLUMN stage_latencies TYPE jsonb"
        " USING stage_latencies::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE rag_request_observations"
        " ALTER COLUMN stage_latencies TYPE json"
        " USING stage_latencies::json"
    )
