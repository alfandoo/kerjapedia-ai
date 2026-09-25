"""normalize RBAC and version governance tables (additive only)

Revision ID: 20260923_0016
Revises: 20260922_0015
Create Date: 2026-09-23

Additive: creates `roles`, `user_roles`, `prompt_versions`, and
`calculation_rules`. `user_profiles.roles` JSONB is kept as a read cache and
backfilled into `user_roles`, never dropped. Neon remains the system of
record; no vector, file, or existing-table changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260923_0016"
down_revision: str | None = "20260922_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWN_ROLES = ("admin", "legal_reviewer", "user", "guest")


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("name"),
    )
    for role in _KNOWN_ROLES:
        op.execute(
            sa.text("INSERT INTO roles (name) VALUES (:name) ON CONFLICT DO NOTHING").bindparams(
                name=role
            )
        )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("role_name", sa.String(length=40), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(length=160), nullable=False, server_default="system"),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.user_id"]),
        sa.ForeignKeyConstraint(["role_name"], ["roles.name"]),
        sa.PrimaryKeyConstraint("user_id", "role_name"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False)
    # Backfill normalized rows from the legacy JSONB cache (known roles only).
    op.execute(
        sa.text(
            "INSERT INTO user_roles (user_id, role_name, assigned_at, assigned_by) "
            "SELECT p.user_id, r.role_name, NOW(), 'migration-0016' "
            "FROM user_profiles p, "
            "LATERAL (SELECT jsonb_array_elements_text(p.roles) AS role_name) r "
            "WHERE r.role_name IN ('admin', 'legal_reviewer', 'user', 'guest') "
            "ON CONFLICT (user_id, role_name) DO NOTHING"
        )
    )
    op.create_table(
        "prompt_versions",
        sa.Column("version_id", sa.String(length=160), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(length=160), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("version_id"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_prompt_versions_status",
        ),
    )
    op.create_index(
        "uq_prompt_versions_single_active",
        "prompt_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "calculation_rules",
        sa.Column("rule_id", sa.String(length=160), nullable=False),
        sa.Column("rule_type", sa.String(length=40), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("legal_source", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("formula_identifier", sa.String(length=120), nullable=False),
        sa.Column("parameters", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("rule_id"),
        sa.UniqueConstraint("rule_type", "version", name="uq_calculation_rules_type_version"),
        sa.CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_calculation_rules_status",
        ),
    )
    op.create_index(
        "ix_calculation_rules_type_status", "calculation_rules", ["rule_type", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_calculation_rules_type_status", table_name="calculation_rules")
    op.drop_table("calculation_rules")
    op.drop_index("uq_prompt_versions_single_active", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("roles")
