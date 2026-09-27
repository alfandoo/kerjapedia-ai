"""Retain token audit rows when conversations are deleted."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260927_0019"
down_revision: str | None = "20260927_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_chat_token_usage_conversation_id_conversations",
        "chat_token_usage",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "fk_chat_token_usage_conversation_id_conversations",
        "chat_token_usage",
        "conversations",
        ["conversation_id"],
        ["conversation_id"],
    )
