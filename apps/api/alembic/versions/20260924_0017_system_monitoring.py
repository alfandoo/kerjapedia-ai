"""system monitoring tables for /admin/system (additive only)

Revision ID: 20260924_0017
Revises: 20260923_0016
Create Date: 2026-09-24

Additive: `http_request_buckets` (per-minute aggregates, never per-request
rows), `dependency_probes`, `system_logs` (errors/warnings only),
`request_traces` (errors/timeouts/slow/sampled only), and `alert_events`.
Retention is enforced by the `kerjapedia.system.cleanup` beat task, so none
of these tables grows without bound. No existing-table changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260924_0017"
down_revision: str | None = "20260923_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "http_request_buckets",
        sa.Column("bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("route", sa.String(length=160), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("status_class", sa.String(length=10), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "sum_latency_ms", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("latency_histogram", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("bucket", "route", "method", "status_class"),
    )
    op.create_table(
        "dependency_probes",
        sa.Column("probe_id", sa.BigInteger(), nullable=False),
        sa.Column("service", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("probe_id"),
        sa.CheckConstraint(
            "status IN ('healthy', 'degraded', 'down', 'unknown')",
            name="ck_dependency_probes_status",
        ),
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS dependency_probes_probe_id_seq")
    op.execute(
        "ALTER TABLE dependency_probes ALTER COLUMN probe_id "
        "SET DEFAULT nextval('dependency_probes_probe_id_seq')"
    )
    op.create_index(
        "ix_dependency_probes_service_checked",
        "dependency_probes",
        ["service", "checked_at"],
        unique=False,
    )
    op.create_table(
        "system_logs",
        sa.Column("log_id", sa.String(length=120), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("service", sa.String(length=80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("trace_id", sa.String(length=80), nullable=True),
        sa.Column("route", sa.String(length=160), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("log_id"),
        sa.CheckConstraint(
            "level IN ('debug', 'info', 'warn', 'error')",
            name="ck_system_logs_level",
        ),
    )
    op.create_index(
        "ix_system_logs_created", "system_logs", ["created_at"], unique=False
    )
    op.create_index(
        "ix_system_logs_trace", "system_logs", ["trace_id"], unique=False
    )
    op.create_table(
        "request_traces",
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("route", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("span_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spans", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("trace_id"),
    )
    op.create_index(
        "ix_request_traces_started", "request_traces", ["started_at"], unique=False
    )
    op.create_table(
        "alert_events",
        sa.Column("alert_id", sa.String(length=120), nullable=False),
        sa.Column("rule", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("alert_id"),
        sa.CheckConstraint(
            "severity IN ('warning', 'critical')",
            name="ck_alert_events_severity",
        ),
        sa.CheckConstraint(
            "status IN ('firing', 'resolved')",
            name="ck_alert_events_status",
        ),
    )
    op.create_index(
        "ix_alert_events_rule_status", "alert_events", ["rule", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_alert_events_rule_status", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_request_traces_started", table_name="request_traces")
    op.drop_table("request_traces")
    op.drop_index("ix_system_logs_trace", table_name="system_logs")
    op.drop_index("ix_system_logs_created", table_name="system_logs")
    op.drop_table("system_logs")
    op.drop_index(
        "ix_dependency_probes_service_checked", table_name="dependency_probes"
    )
    op.drop_table("dependency_probes")
    op.execute("DROP SEQUENCE IF EXISTS dependency_probes_probe_id_seq")
    op.drop_table("http_request_buckets")
