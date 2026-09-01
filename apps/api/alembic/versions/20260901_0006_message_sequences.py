"""add deterministic per-conversation message sequences

Revision ID: 20260901_0006
Revises: 20260830_0005
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0006"
down_revision: str | None = "20260830_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("sequence_no", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH ranked AS (
            SELECT
                message_id,
                ROW_NUMBER() OVER (
                    PARTITION BY conversation_id
                    ORDER BY created_at NULLS LAST, message_id
                ) AS sequence_no
            FROM messages
        )
        UPDATE messages
        SET sequence_no = ranked.sequence_no
        FROM ranked
        WHERE messages.message_id = ranked.message_id
        """
    )
    op.alter_column("messages", "sequence_no", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint(
        "sequence_positive",
        "messages",
        "sequence_no > 0",
    )
    op.create_unique_constraint(
        "uq_messages_conversation_sequence",
        "messages",
        ["conversation_id", "sequence_no"],
    )
    op.create_index(
        "ix_messages_conversation_recent",
        "messages",
        ["conversation_id", "sequence_no", "message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_recent", table_name="messages")
    op.drop_constraint(
        "uq_messages_conversation_sequence",
        "messages",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_messages_sequence_positive"),
        "messages",
        type_="check",
    )
    op.drop_column("messages", "sequence_no")
