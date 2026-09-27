"""Add explicit work profiles and per-conversation personalization."""

from alembic import op
import sqlalchemy as sa

revision = "20260927_0022"
down_revision = "20260927_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_profiles",
        sa.Column("user_id", sa.String(80), sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("province", sa.String(80), nullable=True),
        sa.Column("employment_status", sa.String(20), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monthly_wage", sa.Integer(), nullable=True),
    )
    op.add_column("conversations", sa.Column("personalized_mode", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("conversations", "personalized_mode")
    op.drop_table("work_profiles")
