"""Add account-level memories generated from completed user chats."""

from alembic import op
import sqlalchemy as sa

revision = "20260928_0023"
down_revision = "20260927_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_memory_settings",
        sa.Column("user_id", sa.String(80), sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_memories",
        sa.Column("memory_id", sa.String(120), primary_key=True),
        sa.Column("user_id", sa.String(80), sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_message_id", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "source_message_id", name="uq_user_memories_source"),
    )
    op.create_index("ix_user_memories_recent", "user_memories", ["user_id", "updated_at", "memory_id"])


def downgrade() -> None:
    op.drop_index("ix_user_memories_recent", table_name="user_memories")
    op.drop_table("user_memories")
    op.drop_table("user_memory_settings")
