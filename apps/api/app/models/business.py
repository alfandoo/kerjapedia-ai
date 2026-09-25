from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Sequence as sa_Sequence
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class PendingRegistration(Base):
    """Deferred email signup: no Supabase user is created until the OTP is
    verified. The password is stored encrypted (Fernet), never in plaintext.
    """

    __tablename__ = "pending_registrations"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    # Legacy read cache; `user_roles` is authoritative since migration 0016.
    roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Role(Base):
    """Known RBAC role names; `user_roles` carries the assignments."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class UserRole(Base):
    """Normalized role assignment; authoritative over `UserProfile.roles`."""

    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id"), primary_key=True
    )
    role_name: Mapped[str] = mapped_column(
        ForeignKey("roles.name"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    assigned_by: Mapped[str] = mapped_column(String(160), nullable=False, default="system")


class PromptVersion(Base):
    """Versioned system/developer prompt; single active row drives generation."""

    __tablename__ = "prompt_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_prompt_versions_status",
        ),
        Index(
            "uq_prompt_versions_single_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    version_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_by: Mapped[str] = mapped_column(String(160), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CalculationRule(Base):
    """Versioned deterministic calculator rule with legal source and dates."""

    __tablename__ = "calculation_rules"
    __table_args__ = (
        UniqueConstraint("rule_type", "version", name="uq_calculation_rules_type_version"),
        CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_calculation_rules_status",
        ),
        Index("ix_calculation_rules_type_status", "rule_type", "status"),
    )

    rule_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_source: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date)
    formula_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.user_id"), nullable=True)
    guest_id: Mapped[str | None] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("sequence_no > 0", name="sequence_positive"),
        UniqueConstraint(
            "conversation_id",
            "sequence_no",
            name="uq_messages_conversation_sequence",
        ),
        Index(
            "ix_messages_conversation_recent",
            "conversation_id",
            "sequence_no",
            "message_id",
        ),
    )

    message_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.conversation_id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    feedback_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(80))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_id: Mapped[str | None] = mapped_column(String(120))
    conversation_id: Mapped[str | None] = mapped_column(String(80))
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_category: Mapped[str | None] = mapped_column(String(80))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"

    dataset_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationQuestionReview(Base):
    __tablename__ = "evaluation_question_reviews"
    __table_args__ = (
        Index(
            "ix_evaluation_question_review_latest",
            "dataset_id",
            "question_id",
            "reviewed_at",
            "review_id",
        ),
        CheckConstraint(
            "status IN ('verified', 'rejected')",
            name="ck_evaluation_question_review_status",
        ),
    )

    review_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_datasets.dataset_id"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_datasets.dataset_id"), nullable=False
    )
    release_id: Mapped[str | None] = mapped_column(ForeignKey("rag_index_releases.release_id"))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    progress_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentAdmin(Base):
    __tablename__ = "document_admin"

    document_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    relationships: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    versions_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="System")


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    upload_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(80), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(160))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyUsage(Base):
    """Per-identity token/request metering for cost and anomaly review."""

    __tablename__ = "daily_usage"

    user_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RagRequestObservation(Base):
    """One durable row per completed chat turn for the observability page."""

    __tablename__ = "rag_request_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    request_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    llm_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    claims_supported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claims_unsupported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topic: Mapped[str] = mapped_column(String(120), nullable=False, default="unknown")
    is_followup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stage_latencies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class RagProviderError(Base):
    """Provider failure events; kept separate so failed turns stay countable."""

    __tablename__ = "rag_provider_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)


class HttpRequestBucket(Base):
    """Per-minute HTTP aggregates; never per-request rows (bounded growth)."""

    __tablename__ = "http_request_buckets"

    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    route: Mapped[str] = mapped_column(String(160), primary_key=True)
    method: Mapped[str] = mapped_column(String(10), primary_key=True)
    status_class: Mapped[str] = mapped_column(String(10), primary_key=True)
    count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sum_latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    latency_histogram: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class DependencyProbe(Base):
    """Health probe result per dependency; retention prunes old rows."""

    __tablename__ = "dependency_probes"

    probe_id: Mapped[int] = mapped_column(
        BigInteger,
        sa_Sequence("dependency_probes_probe_id_seq"),
        primary_key=True,
    )
    service: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemLog(Base):
    """Queryable warn/error log; info/debug stay on stdout only (volume)."""

    __tablename__ = "system_logs"
    __table_args__ = (
        Index("ix_system_logs_created", "created_at"),
        Index("ix_system_logs_trace", "trace_id"),
    )

    log_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    service: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80))
    trace_id: Mapped[str | None] = mapped_column(String(80))
    route: Mapped[str | None] = mapped_column(String(160))
    status_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequestTrace(Base):
    """Persisted trace: errors/timeouts/slow/sampled only (bounded growth)."""

    __tablename__ = "request_traces"
    __table_args__ = (Index("ix_request_traces_started", "started_at"),)

    trace_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    route: Mapped[str] = mapped_column(String(160), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    span_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spans: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class AlertEvent(Base):
    """Firing/resolved alert history; rules are code-driven (see alerts.py)."""

    __tablename__ = "alert_events"
    __table_args__ = (Index("ix_alert_events_rule_status", "rule", "status"),)

    alert_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    rule: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="firing")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RagRagasEval(Base):
    """Online RAGAS evaluation attempts with their sampled score."""

    __tablename__ = "rag_ragas_evals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
