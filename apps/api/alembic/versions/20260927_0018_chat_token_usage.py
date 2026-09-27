"""Per-turn token usage and reservation ledger."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0018"
down_revision: str | None = "20260924_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_token_usage",
        sa.Column("turn_id", sa.String(120), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(80),
            sa.ForeignKey("conversations.conversation_id"),
            nullable=False,
        ),
        sa.Column("identity_key", sa.String(160), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("estimated_prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("provider_started", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_chat_token_usage_identity_day", "chat_token_usage", ["identity_key", "usage_date"]
    )
    op.create_index("ix_chat_token_usage_conversation", "chat_token_usage", ["conversation_id"])
    op.execute(
        sa.text("""
        INSERT INTO chat_token_usage
            (turn_id, conversation_id, identity_key, usage_date,
             prompt_tokens, completion_tokens, source, status,
             provider_started, created_at, updated_at)
        SELECT m.message_id, m.conversation_id,
               CASE WHEN c.user_id IS NOT NULL THEN c.user_id ELSE 'guest:' || c.guest_id END,
               (m.created_at AT TIME ZONE 'Asia/Jakarta')::date,
               CASE WHEN COALESCE((m.metadata->'token_usage'->>'prompt_tokens')::bigint, 0) > 0
                    THEN (m.metadata->'token_usage'->>'prompt_tokens')::bigint
                    ELSE GREATEST(2000, CEIL(LENGTH(COALESCE(q.content, '')) / 4.0)::bigint + 3500)
               END,
               CASE WHEN COALESCE((m.metadata->'token_usage'->>'completion_tokens')::bigint, 0) > 0
                    THEN (m.metadata->'token_usage'->>'completion_tokens')::bigint
                    ELSE GREATEST(1, CEIL(LENGTH(m.content) / 4.0)::bigint)
               END,
               CASE WHEN COALESCE((m.metadata->'token_usage'->>'prompt_tokens')::bigint, 0) > 0
                         AND COALESCE(
                             (m.metadata->'token_usage'->>'completion_tokens')::bigint, 0
                         ) > 0
                    THEN 'provider' ELSE 'estimated' END,
               'completed', true, m.created_at, m.created_at
        FROM messages m JOIN conversations c ON c.conversation_id = m.conversation_id
        LEFT JOIN LATERAL (
            SELECT u.content FROM messages u
            WHERE u.conversation_id = m.conversation_id
              AND u.role = 'user' AND u.sequence_no < m.sequence_no
            ORDER BY u.sequence_no DESC LIMIT 1
        ) q ON true
        WHERE m.role = 'assistant' AND (c.user_id IS NOT NULL OR c.guest_id IS NOT NULL)
    """)
    )
    op.execute(
        sa.text("""
        INSERT INTO daily_usage (user_key, usage_date, requests, prompt_tokens,
                                 completion_tokens, updated_at)
        SELECT identity_key, usage_date, COUNT(*)::integer, SUM(prompt_tokens),
               SUM(completion_tokens), NOW()
        FROM chat_token_usage GROUP BY identity_key, usage_date
        ON CONFLICT (user_key, usage_date) DO UPDATE SET
            requests = GREATEST(daily_usage.requests, EXCLUDED.requests),
            prompt_tokens = GREATEST(daily_usage.prompt_tokens, EXCLUDED.prompt_tokens),
            completion_tokens = GREATEST(daily_usage.completion_tokens, EXCLUDED.completion_tokens),
            updated_at = NOW()
    """)
    )


def downgrade() -> None:
    op.drop_index("ix_chat_token_usage_conversation", table_name="chat_token_usage")
    op.drop_index("ix_chat_token_usage_identity_day", table_name="chat_token_usage")
    op.drop_table("chat_token_usage")
