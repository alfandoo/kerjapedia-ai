"""Track chat latency and outcomes by reasoning mode."""

from alembic import op
import sqlalchemy as sa

revision = "20260927_0021"
down_revision = "20260927_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_request_observations", sa.Column("turn_id", sa.String(120), nullable=True))
    op.add_column("rag_request_observations", sa.Column("reasoning_mode", sa.String(20), nullable=False, server_default="standard"))
    op.add_column("rag_request_observations", sa.Column("time_to_first_status_ms", sa.Float(), nullable=True))
    op.add_column("rag_request_observations", sa.Column("time_to_first_content_ms", sa.Float(), nullable=True))
    op.add_column("rag_request_observations", sa.Column("disconnected", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("rag_request_observations", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("rag_request_observations", sa.Column("provider_failure", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_unique_constraint("uq_rag_request_observations_turn_id", "rag_request_observations", ["turn_id"])


def downgrade() -> None:
    op.drop_constraint("uq_rag_request_observations_turn_id", "rag_request_observations", type_="unique")
    for column in ("provider_failure", "retry_count", "disconnected", "time_to_first_content_ms", "time_to_first_status_ms", "reasoning_mode", "turn_id"):
        op.drop_column("rag_request_observations", column)
