from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import Float as sa_Float
from sqlalchemy import cast as sa_cast
from sqlalchemy import func as sa_func
from sqlalchemy import text as sa_text

from app.api.dependencies import AdminUser, DbSession
from app.api.schemas import (
    DocumentRelationshipRequest,
    DocumentUpdateRequest,
    DocumentVerificationRequest,
    IngestionBuildReviewRequest,
    PublicationRequest,
    RetrievalPlaygroundRequest,
)
from app.api.state import now_utc
from app.api.utils import (
    dataset_metadata_path,
    find_dataset_document,
    load_dataset_documents,
    storage_root,
)
from app.api.utils import project_root as get_project_root
from app.core.config import settings
from app.models.business import (
    Conversation,
    DailyUsage,
    DocumentAdmin,
    Feedback,
    Message,
    RagProviderError,
    RagRagasEval,
    RagRequestObservation,
    UploadedDocument,
    UserProfile,
)
from app.models.ingestion import (
    Document,
    DocumentRelationship,
    DocumentVerificationAudit,
    DocumentVersion,
    IngestionBuild,
    IngestionJob,
)
from app.services.audit import list_audit_logs, log_audit
from app.services.ingestion.governance import is_canonical_official_source_url
from app.services.ingestion.manifest_updater import (
    MANIFEST_EDITABLE_FIELDS,
    manifest_contains,
    update_manifest_metadata,
)
from app.services.ingestion.uploads import (
    load_uploads_manifest,
    merge_documents,
    register_upload,
)
from app.services.providers import reset_provider_caches
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.relationships import relationship_index_for_manifest
from app.services.retrieval.store import load_artifact_documents
from app.services.storage import upload_bytes

router = APIRouter(prefix="/admin", tags=["admin"])

_stats_cache: dict[str, tuple[float, dict]] = {}
_docs_cache: dict[str, tuple[float, dict]] = {}
_STATS_CACHE_TTL = 30  # seconds
_DOCS_CACHE_TTL = 30
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def project_root() -> Path:
    return get_project_root()


def _manifest_relationships() -> list[dict]:
    data = json.loads(dataset_metadata_path().read_text(encoding="utf-8"))
    return data.get("relationships", [])


def _now_iso() -> str:
    return now_utc().isoformat()


def _latest_document_version(session, document_id: str) -> DocumentVersion | None:
    return (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(
            DocumentVersion.created_at.desc().nullslast(),
            DocumentVersion.version.desc(),
            DocumentVersion.version_id.desc(),
        )
        .first()
    )


def _get_or_create_admin_record(document_id: str, session) -> DocumentAdmin:
    record = session.get(DocumentAdmin, document_id)
    if record is None:
        relationships = [
            item for item in _manifest_relationships() if item["from_document_id"] == document_id
        ]
        record = DocumentAdmin(
            document_id=document_id,
            publication_status="draft",
            version=1,
            relationships=relationships,
            versions_history=[
                {
                    "version": 1,
                    "status": "draft",
                    "created_at": _now_iso(),
                    "created_by": "System",
                }
            ],
        )
        session.add(record)
        session.commit()
    return record


def _latest_jobs(session) -> dict[str, dict]:
    from app.models.ingestion import IngestionJob

    jobs: dict[str, dict] = {}
    rows = session.query(IngestionJob).order_by(IngestionJob.created_at.desc()).all()
    for job in rows:
        jobs.setdefault(
            job.document_id,
            {
                "job_id": job.job_id,
                "document_id": job.document_id,
                "status": job.status,
                "error": None,
                "updated_at": job.created_at,
            },
        )
    return jobs


def _admin_ingestion_status(version: DocumentVersion | None) -> str:
    """Keep the existing admin API label while using DB governance as truth."""
    if version is None:
        return "needs_review"
    if version.ingestion_status == "review_required":
        return "needs_review"
    return version.ingestion_status


def _usage_summary(session) -> dict:
    """Token/request metering per identity: today totals plus top consumers."""
    from datetime import date, timedelta

    today = date.today()
    week_ago = today - timedelta(days=7)
    today_rows = session.query(DailyUsage).filter(DailyUsage.usage_date == today).all()
    top_rows = (
        session.query(
            DailyUsage.user_key,
            sa_func.sum(DailyUsage.requests).label("requests"),
            sa_func.sum(DailyUsage.prompt_tokens).label("prompt_tokens"),
            sa_func.sum(DailyUsage.completion_tokens).label("completion_tokens"),
        )
        .filter(DailyUsage.usage_date >= week_ago)
        .group_by(DailyUsage.user_key)
        .order_by(
            sa_func.sum(DailyUsage.prompt_tokens + DailyUsage.completion_tokens).desc()
        )
        .limit(10)
        .all()
    )
    return {
        "today": {
            "requests": sum(row.requests or 0 for row in today_rows),
            "prompt_tokens": sum(row.prompt_tokens or 0 for row in today_rows),
            "completion_tokens": sum(row.completion_tokens or 0 for row in today_rows),
            "identities": len(today_rows),
        },
        "top_7d": [
            {
                "user_key": row.user_key,
                "requests": int(row.requests or 0),
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
            }
            for row in top_rows
        ],
    }


@router.get("/stats")
def admin_stats(session: DbSession, _: AdminUser) -> dict:
    cache_key = "stats"
    cached = _stats_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _STATS_CACHE_TTL:
        return cached[1]

    documents = load_dataset_documents()
    doc_counts = {
        "total": len(documents),
        "published": 0,
        "needs_review": 0,
        "failed": 0,
    }
    for doc in documents:
        version = _latest_document_version(session, doc.document_id)
        pub = version.publication_status if version else "draft"
        ing_status = _admin_ingestion_status(version)
        if pub == "published":
            doc_counts["published"] += 1
        if ing_status == "needs_review":
            doc_counts["needs_review"] += 1
        if ing_status == "failed":
            doc_counts["failed"] += 1

    user_count = session.query(UserProfile).count()
    conversation_count = session.query(Conversation).count()
    message_count = session.query(sa_func.count(Message.message_id)).scalar() or 0
    feedback_count = session.query(Feedback).count()
    feedback_helpful = session.query(Feedback).filter(Feedback.rating == "helpful").count()
    job_count = session.query(IngestionJob).count()
    recent_jobs = (
        session.query(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(5).all()
    )

    result = {
        "documents": doc_counts,
        "users": user_count,
        "conversations": conversation_count,
        "messages": message_count,
        "usage": _usage_summary(session),
        "feedback": {
            "total": feedback_count,
            "helpful": feedback_helpful,
            "not_helpful": feedback_count - feedback_helpful,
        },
        "ingestion_jobs": {
            "total": job_count,
            "recent": [
                {
                    "job_id": j.job_id,
                    "document_id": j.document_id,
                    "status": j.status,
                    "created_at": j.created_at.isoformat(),
                }
                for j in recent_jobs
            ],
        },
    }
    _stats_cache[cache_key] = (time.time(), result)
    return result


@router.get("/usage/daily")
def admin_usage_daily(
    session: DbSession,
    _: AdminUser,
    days: int = Query(default=30, ge=1, le=90),
) -> dict:
    """Per-day usage trend for the dashboard (zero-filled, oldest first)."""
    today = now_utc().date()
    start_day = today - timedelta(days=days - 1)
    start_at = datetime.combine(start_day, datetime.min.time()).replace(tzinfo=UTC)

    message_rows = (
        session.query(
            sa_func.date(Message.created_at).label("day"),
            sa_func.count(Message.message_id),
        )
        .filter(Message.role == "user", Message.created_at >= start_at)
        .group_by(sa_func.date(Message.created_at))
        .all()
    )
    conversation_rows = (
        session.query(
            sa_func.date(Conversation.created_at).label("day"),
            sa_func.count(Conversation.conversation_id),
        )
        .filter(Conversation.created_at >= start_at)
        .group_by(sa_func.date(Conversation.created_at))
        .all()
    )
    active_rows = (
        session.query(
            DailyUsage.usage_date,
            sa_func.count(sa_func.distinct(DailyUsage.user_key)),
        )
        .filter(DailyUsage.usage_date >= start_day)
        .group_by(DailyUsage.usage_date)
        .all()
    )

    messages_by_day = {str(row[0]): int(row[1]) for row in message_rows}
    conversations_by_day = {str(row[0]): int(row[1]) for row in conversation_rows}
    active_by_day = {str(row[0]): int(row[1]) for row in active_rows}

    points = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        key = day.isoformat()
        points.append(
            {
                "date": key,
                "messages": messages_by_day.get(key, 0),
                "conversations": conversations_by_day.get(key, 0),
                "active_users": active_by_day.get(key, 0),
            }
        )
    return {"days": days, "points": points}


def _metrics_histogram(rows: list[tuple]) -> dict[str, dict[str, float | None]]:
    """Reshape SQL percentile rows into the histogram stats shape the UI reads."""
    stats: dict[str, dict[str, float | None]] = {}
    for key, count, total, p50, p95, p99 in rows:
        stats[str(key)] = {
            "count": float(count or 0),
            "sum": float(total or 0),
            "avg": (float(total) / float(count)) if count else None,
            "p50": float(p50) if p50 is not None else None,
            "p95": float(p95) if p95 is not None else None,
            "p99": float(p99) if p99 is not None else None,
        }
    return stats


def _pct(fraction: float):
    return sa_func.percentile_cont(sa_cast(fraction, sa_Float))


@router.get("/metrics")
def admin_metrics(session: DbSession, _: AdminUser) -> dict:
    """Aggregate durable per-request observations (survives restarts)."""
    outcomes = {
        str(row[0]): int(row[1])
        for row in session.query(
            RagRequestObservation.outcome, sa_func.count(RagRequestObservation.id)
        )
        .group_by(RagRequestObservation.outcome)
        .all()
    }
    request_count = int(
        session.query(sa_func.count(RagRequestObservation.id)).scalar() or 0
    )
    stage_rows = session.execute(
        sa_text(
            "SELECT s->>'stage' AS stage,"
            " COUNT(*) AS count,"
            " SUM((s->>'seconds')::double precision) AS total,"
            " percentile_cont(0.5::double precision) WITHIN GROUP"
            " (ORDER BY (s->>'seconds')::double precision) AS p50,"
            " percentile_cont(0.95::double precision) WITHIN GROUP"
            " (ORDER BY (s->>'seconds')::double precision) AS p95,"
            " percentile_cont(0.99::double precision) WITHIN GROUP"
            " (ORDER BY (s->>'seconds')::double precision) AS p99"
            " FROM rag_request_observations, jsonb_array_elements(stage_latencies) AS s"
            " GROUP BY s->>'stage'"
        )
    ).all()
    stage_latency = _metrics_histogram(
        [(row[0], row[1], row[2], row[3], row[4], row[5]) for row in stage_rows]
    )
    latency_row = (
        session.query(
            sa_func.count(RagRequestObservation.id),
            sa_func.sum(RagRequestObservation.request_latency_ms),
            _pct(0.5).within_group(RagRequestObservation.request_latency_ms),
            _pct(0.95).within_group(RagRequestObservation.request_latency_ms),
            _pct(0.99).within_group(RagRequestObservation.request_latency_ms),
        )
        .filter(RagRequestObservation.request_latency_ms.is_not(None))
        .one()
    )
    request_latency = _metrics_histogram(
        [("all", latency_row[0] or 0, (latency_row[1] or 0) / 1000.0, *[
            (value / 1000.0) if value is not None else None for value in latency_row[2:]
        ])]
    ).get("all", {})
    token_rows = (
        session.query(
            RagRequestObservation.llm_model,
            sa_func.sum(RagRequestObservation.prompt_tokens),
            sa_func.sum(RagRequestObservation.completion_tokens),
        )
        .group_by(RagRequestObservation.llm_model)
        .all()
    )
    tokens_by_model = {
        str(model or "unknown"): {
            "prompt": int(prompt or 0),
            "completion": int(completion or 0),
        }
        for model, prompt, completion in token_rows
    }
    prompt_tokens = sum(entry["prompt"] for entry in tokens_by_model.values())
    completion_tokens = sum(entry["completion"] for entry in tokens_by_model.values())
    supported, unsupported = (
        session.query(
            sa_func.sum(RagRequestObservation.claims_supported),
            sa_func.sum(RagRequestObservation.claims_unsupported),
        ).one()
    )
    supported, unsupported = int(supported or 0), int(unsupported or 0)
    claim_total = supported + unsupported
    provider_rows = (
        session.query(RagProviderError.stage, sa_func.count(RagProviderError.id))
        .group_by(RagProviderError.stage)
        .all()
    )
    provider_errors = {str(stage): int(count) for stage, count in provider_rows}
    ragas_rows = (
        session.query(RagRagasEval.status, sa_func.count(RagRagasEval.id))
        .group_by(RagRagasEval.status)
        .all()
    )
    ragas_eval = {str(status): int(count) for status, count in ragas_rows}
    faithfulness_row = (
        session.query(
            sa_func.count(RagRagasEval.score),
            sa_func.sum(RagRagasEval.score),
            _pct(0.5).within_group(RagRagasEval.score),
            _pct(0.95).within_group(RagRagasEval.score),
            _pct(0.99).within_group(RagRagasEval.score),
        )
        .filter(RagRagasEval.score.is_not(None))
        .one()
    )
    faithfulness_count = int(faithfulness_row[0] or 0)
    faithfulness_sum = float(faithfulness_row[1] or 0)
    faithfulness = {
        "count": float(faithfulness_count),
        "sum": faithfulness_sum,
        "avg": (faithfulness_sum / faithfulness_count) if faithfulness_count else None,
        "p50": float(faithfulness_row[2]) if faithfulness_row[2] is not None else None,
        "p95": float(faithfulness_row[3]) if faithfulness_row[3] is not None else None,
        "p99": float(faithfulness_row[4]) if faithfulness_row[4] is not None else None,
    }
    behavior_total = request_count
    followups = int(
        session.query(sa_func.count(RagRequestObservation.id))
        .filter(RagRequestObservation.is_followup.is_(True))
        .scalar()
        or 0
    )
    behavior_by_topic = {
        str(topic): int(count)
        for topic, count in session.query(
            RagRequestObservation.topic, sa_func.count(RagRequestObservation.id)
        )
        .group_by(RagRequestObservation.topic)
        .all()
    }
    return {
        "ragas_enabled": settings.ragas_enabled,
        "ragas_sample_rate": settings.ragas_sample_rate,
        "outcomes": outcomes,
        "requests": {
            "total": request_count,
            "by_status": outcomes,
        },
        "stage_latency": stage_latency,
        "request_latency": request_latency,
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
            "by_model": tokens_by_model,
        },
        "claims": {
            "supported": supported,
            "unsupported": unsupported,
            "total": claim_total,
            "support_rate": (supported / claim_total) if claim_total else None,
        },
        "provider_errors": {
            "total": sum(provider_errors.values()),
            "by_stage": provider_errors,
        },
        "ragas": {
            "eval_total": ragas_eval,
            "faithfulness": faithfulness,
        },
        "behavior": {
            "total": behavior_total,
            "followups": followups,
            "followup_ratio": (followups / behavior_total) if behavior_total else None,
            "by_topic": behavior_by_topic,
        },
    }


@router.post("/chat/purge")
def purge_old_chats(
    session: DbSession,
    _: AdminUser,
    days: int = Query(default=-1, ge=-1, le=3650),
) -> dict:
    """Delete conversations untouched for `days` (default: retention setting)."""
    from app.api.routes_chat import purge_expired_conversations

    retention = settings.chat_retention_days if days < 0 else days
    deleted = purge_expired_conversations(session, retention)
    log_audit(
        actor="admin",
        action="chat_purge",
        target_type="conversations",
        details={"retention_days": retention, **deleted},
    )
    return {"retention_days": retention, **deleted}


@router.get("/documents")
def list_admin_documents(session: DbSession, _: AdminUser) -> dict:
    cache_key = "documents"
    cached = _docs_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _DOCS_CACHE_TTL:
        return cached[1]

    documents = merge_documents(
        load_dataset_documents(),
        load_uploads_manifest(storage_root()),
    )
    chunks = load_artifact_documents(storage_root())
    chunk_counts: dict[str, int] = {}
    for chunk in chunks:
        chunk_counts[chunk.document_id] = chunk_counts.get(chunk.document_id, 0) + 1
    results = []

    for _index, document in enumerate(documents):
        record = _get_or_create_admin_record(document.document_id, session)
        version = _latest_document_version(session, document.document_id)
        ingestion_status = _admin_ingestion_status(version)
        payload = asdict(document)
        payload.update(record.overrides)
        payload.update(
            {
                "ingestion_status": ingestion_status,
                "chunk_count": chunk_counts.get(document.document_id, 0),
                "publication_status": version.publication_status if version else "draft",
                "source_verification_status": version.source_verification_status
                if version
                else "pending",
                "legal_review_status": version.legal_review_status if version else "pending",
                "version": version.version if version else record.version,
                "updated_at": record.updated_at,
                "updated_by": record.updated_by,
                "relationships": record.relationships,
                "versions": list(reversed(record.versions_history)),
                "last_error": None,
            }
        )
        results.append(payload)

    summary = {
        "documents": len(results),
        "published": sum(item["publication_status"] == "published" for item in results),
        "needs_review": sum(item["ingestion_status"] == "needs_review" for item in results),
        "failed": sum(item["ingestion_status"] == "failed" for item in results),
    }
    result = {"summary": summary, "documents": results}
    _docs_cache[cache_key] = (time.time(), result)
    return result


@router.patch("/documents/{document_id}")
def update_admin_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    session: DbSession,
    user: AdminUser,
) -> dict:
    _stats_cache.clear()
    _docs_cache.clear()
    dataset_path = dataset_metadata_path()
    changes = payload.model_dump(exclude_none=True)

    manifest_path = dataset_path
    if not manifest_contains(manifest_path, document_id):
        upload_path = storage_root() / "uploads" / "manifest.json"
        if manifest_contains(upload_path, document_id):
            manifest_path = upload_path
        else:
            find_dataset_document(document_id)

    applied: dict = {}
    if changes:
        try:
            applied = update_manifest_metadata(manifest_path, document_id, changes)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} was not found.",
            ) from exc

    record = _get_or_create_admin_record(document_id, session)
    record.overrides = {**record.overrides, **applied}
    record.updated_at = now_utc()
    record.updated_by = user.user_id

    if "source_url" in changes:
        version = _latest_document_version(session, document_id)
        if version is not None:
            version.source_url = changes["source_url"]

    session.commit()

    log_audit(
        actor=user.user_id,
        action="document.metadata_updated",
        target_type="document",
        target_id=document_id,
        details={"applied": {key: str(value) for key, value in applied.items()}},
    )
    return {
        "status": "updated",
        "document_id": document_id,
        "applied_changes": applied,
        "editable_fields": sorted(MANIFEST_EDITABLE_FIELDS),
    }


@router.put("/documents/{document_id}/relationships")
def replace_relationships(
    document_id: str,
    payload: list[DocumentRelationshipRequest],
    session: DbSession,
    user: AdminUser,
) -> dict:
    if "legal_reviewer" not in user.roles:
        raise HTTPException(status_code=403, detail="Legal reviewer role is required.")
    find_dataset_document(document_id)
    if session.get(Document, document_id) is None:
        raise HTTPException(status_code=409, detail="Source document has not been ingested.")
    relationships = []
    session.query(DocumentRelationship).filter(
        DocumentRelationship.from_document_id == document_id
    ).delete()
    for relationship in payload:
        find_dataset_document(relationship.to_document_id)
        if session.get(Document, relationship.to_document_id) is None:
            raise HTTPException(
                status_code=409,
                detail=f"Target document {relationship.to_document_id} has not been ingested.",
            )
        if not relationship.evidence_url or not relationship.evidence_url.startswith("https://"):
            raise HTTPException(
                status_code=422,
                detail="A reviewed HTTPS evidence URL is required for every legal relationship.",
            )
        item = {
            "from_document_id": document_id,
            **relationship.model_dump(),
        }
        relationships.append(item)
        session.add(
            DocumentRelationship(
                relationship_id=f"rel_{uuid4().hex}",
                from_document_id=document_id,
                to_document_id=relationship.to_document_id,
                relationship_type=relationship.relationship_type,
                from_article=relationship.from_article,
                to_article=relationship.to_article,
                confidence=relationship.confidence,
                evidence_url=relationship.evidence_url,
                notes=relationship.notes or "",
                reviewed_by=user.user_id,
                reviewed_at=now_utc(),
            )
        )
    record = _get_or_create_admin_record(document_id, session)
    record.relationships = relationships
    record.updated_at = now_utc()
    session.commit()
    reset_provider_caches()
    log_audit(
        actor=user.user_id,
        action="document.relationships_updated",
        target_type="document",
        target_id=document_id,
        details={"relationships": relationships},
    )
    return {"status": "updated", "relationships": relationships}


@router.post("/documents/{document_id}/publication")
def update_publication(
    document_id: str,
    payload: PublicationRequest,
    session: DbSession,
    user: AdminUser,
) -> dict:
    find_dataset_document(document_id)
    record = _get_or_create_admin_record(document_id, session)
    publication_status = "published" if payload.action == "publish" else "draft"
    version = _latest_document_version(session, document_id)
    if payload.action == "publish":
        if version is None:
            raise HTTPException(status_code=409, detail="Document has not been ingested.")
        if (
            version.ingestion_status != "completed"
            or version.source_verification_status != "verified"
            or version.legal_review_status != "verified"
            or not is_canonical_official_source_url(version.source_url)
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Only a completed version with verified source and legal review "
                    "can be published."
                ),
            )
    if version is not None:
        version.publication_status = publication_status
    record.version += 1
    record.publication_status = publication_status
    record.updated_at = now_utc()
    record.versions_history = [
        *record.versions_history,
        {
            "version": record.version,
            "status": publication_status,
            "created_at": _now_iso(),
            "created_by": user.user_id,
        },
    ]
    session.commit()
    reset_provider_caches()
    log_audit(
        actor=user.user_id,
        action=f"document.{publication_status}",
        target_type="document",
        target_id=document_id,
        details={"version": record.version},
    )
    return {
        "status": publication_status,
        "version": record.version,
        "versions": list(reversed(record.versions_history)),
    }


@router.post("/documents/{document_id}/verification")
def verify_document_version(
    document_id: str,
    payload: DocumentVerificationRequest,
    session: DbSession,
    user: AdminUser,
) -> dict:
    if payload.verification_type == "legal" and "legal_reviewer" not in user.roles:
        raise HTTPException(status_code=403, detail="Legal reviewer role is required.")
    version = _latest_document_version(session, document_id)
    if version is None:
        raise HTTPException(status_code=409, detail="Document has not been ingested.")
    if payload.status == "verified" and not is_canonical_official_source_url(payload.evidence_url):
        raise HTTPException(
            status_code=422,
            detail="Verification requires a canonical official government HTTPS URL.",
        )
    if (
        payload.verification_type == "source"
        and payload.status == "verified"
        and not is_canonical_official_source_url(version.source_url)
    ):
        raise HTTPException(
            status_code=409,
            detail="Replace the search URL with a canonical official landing page or PDF first.",
        )
    if payload.verification_type == "source":
        version.source_verification_status = payload.status
    else:
        version.legal_review_status = payload.status
    if payload.status == "verified":
        version.verified_by = user.user_id
        version.verified_at = now_utc()
    session.add(
        DocumentVerificationAudit(
            audit_id=f"verify_{uuid4().hex}",
            version_id=version.version_id,
            verification_type=payload.verification_type,
            status=payload.status,
            reviewer=user.user_id,
            evidence_url=payload.evidence_url,
            notes=payload.notes,
        )
    )
    session.commit()
    reset_provider_caches()
    log_audit(
        actor=user.user_id,
        action=f"document.{payload.verification_type}_verification",
        target_type="document",
        target_id=document_id,
        details={"status": payload.status, "version_id": version.version_id},
    )
    return {
        "document_id": document_id,
        "version_id": version.version_id,
        "source_verification_status": version.source_verification_status,
        "legal_review_status": version.legal_review_status,
        "verified_by": version.verified_by,
        "verified_at": version.verified_at,
    }


@router.post("/ingestion/builds/{build_id}/review")
def review_ingestion_build(
    build_id: str,
    payload: IngestionBuildReviewRequest,
    session: DbSession,
    user: AdminUser,
) -> dict:
    build = (
        session.query(IngestionBuild)
        .filter(IngestionBuild.build_id == build_id)
        .with_for_update()
        .one_or_none()
    )
    if build is None:
        raise HTTPException(status_code=404, detail="Ingestion build was not found.")
    if payload.status == "rejected" and not payload.notes.strip():
        raise HTTPException(status_code=422, detail="A rejection reason is required.")

    report = dict(build.quality_report or {})
    gates = dict(report.get("gates") or {})
    unresolved = {str(page) for page in (report.get("pages") or {}).get("unresolved", [])}
    supplied = {str(page): disposition for page, disposition in payload.page_dispositions.items()}
    if payload.status == "approved":
        missing = sorted(unresolved - set(supplied))
        unexpected = sorted(set(supplied) - unresolved)
        failed_gates = sorted(
            name for name, passed in gates.items() if not passed and name != "no_unresolved_pages"
        )
        if missing or unexpected or failed_gates:
            raise HTTPException(
                status_code=409,
                detail={
                    "missing_page_dispositions": missing,
                    "unexpected_page_dispositions": unexpected,
                    "failed_quality_gates": failed_gates,
                },
            )
        page_dispositions = dict(build.page_dispositions or {})
        page_dispositions.update(supplied)
        build.page_dispositions = page_dispositions
        gates["no_unresolved_pages"] = True
        report["gates"] = gates
        pages = dict(report.get("pages") or {})
        pages["unresolved"] = []
        pages["reviewed_dispositions"] = supplied
        report["pages"] = pages
        report["status"] = "passed"
        build.quality_report = report
        build.status = "completed"
    else:
        build.status = "review_required"

    build.review_status = payload.status
    build.reviewed_by = user.user_id
    build.reviewed_at = now_utc()
    build.review_notes = payload.notes.strip()
    version = session.get(DocumentVersion, build.version_id)
    if version is not None:
        latest_build_id = (version.artifact_paths or {}).get("latest_build_id")
        if latest_build_id == build.build_id:
            version.ingestion_status = (
                "completed" if payload.status == "approved" else "review_required"
            )
    session.commit()
    log_audit(
        actor=user.user_id,
        action=f"ingestion_build.{payload.status}",
        target_type="ingestion_build",
        target_id=build.build_id,
        details={
            "version_id": build.version_id,
            "page_dispositions": supplied,
            "notes": payload.notes.strip(),
        },
    )
    return {
        "build_id": build.build_id,
        "version_id": build.version_id,
        "status": build.status,
        "review_status": build.review_status,
        "quality_report": build.quality_report,
        "page_dispositions": build.page_dispositions,
        "reviewed_by": build.reviewed_by,
        "reviewed_at": build.reviewed_at,
    }



async def _read_upload_content(request: Request) -> bytes:
    """Bound buffering by actual streamed bytes, not the client's size claim."""
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        if not declared_length.isascii() or not declared_length.isdecimal():
            raise HTTPException(status_code=400, detail="Invalid Content-Length.")
        # Avoid parsing an arbitrarily long integer header.
        normalized_length = declared_length.lstrip("0") or "0"
        if len(normalized_length) > len(str(MAX_UPLOAD_BYTES)):
            raise HTTPException(status_code=413, detail="PDF file exceeds the 50 MB limit.")
        if int(normalized_length) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="PDF file exceeds the 50 MB limit.")

    content = bytearray()
    async for chunk in request.stream():
        if len(chunk) > MAX_UPLOAD_BYTES - len(content):
            raise HTTPException(status_code=413, detail="PDF file exceeds the 50 MB limit.")
        content.extend(chunk)
    if declared_length is not None and len(content) != int(normalized_length):
        raise HTTPException(status_code=400, detail="Content-Length does not match the upload.")
    return bytes(content)


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    session: DbSession,
    user: AdminUser,
    file_name: str = Query(min_length=5, max_length=180),
    topic: str = Query(default="uncategorized", min_length=2, max_length=80),
) -> dict:
    safe_name = Path(file_name).name
    if Path(safe_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    content = await _read_upload_content(request)
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")

    upload_id = f"upload_{uuid4().hex}"
    document_id = re.sub(r"[^A-Z0-9]+", "-", Path(safe_name).stem.upper()).strip("-")
    storage_path = f"uploads/{upload_id}_{safe_name}"

    public_url = upload_bytes(content, storage_path)

    uploaded = UploadedDocument(
        upload_id=upload_id,
        document_id=document_id,
        file_name=safe_name,
        storage_path=storage_path,
        topic=topic,
        size_bytes=len(content),
        status="uploaded",
    )
    session.add(uploaded)
    session.commit()

    manifest_document = register_upload(
        storage_root(),
        document_id=document_id,
        file_name=safe_name,
        topic=topic,
        content=content,
        source_url=public_url,
    )
    log_audit(
        actor=user.user_id,
        action="document.uploaded",
        target_type="document",
        target_id=document_id,
        details={
            "file_name": safe_name,
            "topic": topic,
            "size_bytes": len(content),
        },
    )
    return {
        "upload_id": upload_id,
        "document_id": document_id,
        "file_name": safe_name,
        "topic": topic,
        "size_bytes": len(content),
        "status": "uploaded",
        "storage_url": public_url,
        "sha256": manifest_document.sha256,
        "manifest_ready": True,
        "created_at": uploaded.created_at,
    }


@router.post("/retrieval/search")
def retrieval_playground(
    payload: RetrievalPlaygroundRequest,
    _: AdminUser,
) -> dict:
    started_at = time.perf_counter()
    try:
        if settings.vector_store == "upstash_vector":
            from app.services.providers import upstash_vector_store_from_settings

            response = upstash_vector_store_from_settings(settings).search(
                payload.question,
                top_k=payload.top_k,
            )
        else:
            engine = RetrievalEngine(
                documents=load_artifact_documents(storage_root()),
                top_k=payload.top_k,
                relationship_index=relationship_index_for_manifest(dataset_metadata_path()),
                diversity_lambda=settings.retrieval_diversity_lambda,
            )
            response = engine.search(payload.question, top_k=payload.top_k)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    results = []
    for item in response.results:
        document = item.document
        metadata = document.metadata or {}
        if (
            payload.regulation_type
            and metadata.get("regulation_type", "").lower() != payload.regulation_type.lower()
        ):
            continue
        if payload.year is not None and metadata.get("year") != payload.year:
            continue
        if payload.legal_status and document.legal_status != payload.legal_status:
            continue
        results.append(
            {
                "chunk_id": document.chunk_id,
                "document_id": document.document_id,
                "short_title": metadata.get("short_title", document.document_id),
                "article": document.article,
                "page_start": document.page_start,
                "page_end": document.page_end,
                "quote": document.text,
                "lexical_score": item.lexical_score,
                "semantic_score": item.semantic_score,
                "rerank_score": item.rerank_score,
                "final_score": item.final_score,
                "match_reasons": item.match_reasons,
            }
        )
    return {
        "query": payload.question,
        "latency_ms": int((time.perf_counter() - started_at) * 1000),
        "warnings": response.warnings,
        "should_refuse": response.should_refuse,
        "results": results,
    }


@router.get("/settings")
def admin_settings(_: AdminUser) -> dict:
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "admin_email": settings.admin_email,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "vector_store": settings.vector_store,
        "embedding_provider": settings.embedding_provider,
        "llm_provider": settings.llm_provider,
        "session_expires_in_seconds": 3600,
    }


@router.get("/audit-logs")
def audit_logs(
    session: DbSession,
    _: AdminUser,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return list_audit_logs(session, limit=limit)
