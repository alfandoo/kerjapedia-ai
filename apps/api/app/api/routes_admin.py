from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from sqlalchemy import func as sa_func

from app.api.dependencies import AdminUser, DbSession
from app.api.schemas import (
    DocumentRelationshipRequest,
    DocumentUpdateRequest,
    DocumentVerificationRequest,
    IngestionBuildReviewRequest,
    PublicationRequest,
    RagIndexReleaseRequest,
    RagIndexTransitionRequest,
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
    DocumentAdmin,
    EvaluationDataset,
    EvaluationRun,
    Feedback,
    Message,
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
    RagIndexRelease,
)
from app.services.answering.prompts import PROMPT_VERSION_ID
from app.services.audit import list_audit_logs, log_audit
from app.services.evaluation.policy import (
    RELEASE_QUALITY_GATES,
    REQUIRED_RELEASE_SCENARIOS,
)
from app.services.evaluation.reviews import verified_question_reviewers
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
from app.services.providers import pinecone_store_from_settings, reset_provider_caches
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.relationships import (
    relationship_index_for_manifest,
    relationship_snapshot_hash,
)
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
            item
            for item in _manifest_relationships()
            if item["from_document_id"] == document_id
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
    feedback_helpful = (
        session.query(Feedback).filter(Feedback.rating == "helpful").count()
    )
    job_count = session.query(IngestionJob).count()
    recent_jobs = (
        session.query(IngestionJob)
        .order_by(IngestionJob.created_at.desc())
        .limit(5)
        .all()
    )

    result = {
        "documents": doc_counts,
        "users": user_count,
        "conversations": conversation_count,
        "messages": message_count,
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
                "publication_status": version.publication_status
                if version
                else "draft",
                "source_verification_status": version.source_verification_status
                if version
                else "pending",
                "legal_review_status": version.legal_review_status
                if version
                else "pending",
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
        "needs_review": sum(
            item["ingestion_status"] == "needs_review" for item in results
        ),
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
        raise HTTPException(
            status_code=409, detail="Source document has not been ingested."
        )
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
        if not relationship.evidence_url or not relationship.evidence_url.startswith(
            "https://"
        ):
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
            raise HTTPException(
                status_code=409, detail="Document has not been ingested."
            )
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
    elif version is not None and version.is_current:
        active_release = (
            session.query(RagIndexRelease)
            .filter(RagIndexRelease.status == "active")
            .first()
        )
        if active_release is not None:
            raise HTTPException(
                status_code=409,
                detail="Promote a replacement release before unpublishing a current version.",
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
    if payload.status == "verified" and not is_canonical_official_source_url(
        payload.evidence_url
    ):
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
    unresolved = {
        str(page) for page in (report.get("pages") or {}).get("unresolved", [])
    }
    supplied = {
        str(page): disposition
        for page, disposition in payload.page_dispositions.items()
    }
    if payload.status == "approved":
        missing = sorted(unresolved - set(supplied))
        unexpected = sorted(set(supplied) - unresolved)
        failed_gates = sorted(
            name
            for name, passed in gates.items()
            if not passed and name != "no_unresolved_pages"
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


def _ingestion_build_matches_runtime(build: IngestionBuild) -> bool:
    config = build.pipeline_config or {}
    expected = {
        "target_tokens": settings.ingestion_target_tokens,
        "max_tokens": settings.ingestion_max_tokens,
        "overlap_tokens": settings.ingestion_overlap_tokens,
        "min_merge_tokens": settings.ingestion_min_merge_tokens,
        "parent_tokens": settings.ingestion_parent_tokens,
        "embedding_batch_size": settings.ingestion_embedding_batch_size,
        "embedding_dimension": settings.embedding_dimension,
    }
    gates = (build.quality_report or {}).get("gates") or {}
    return bool(
        build.status == "completed"
        and build.review_status == "approved"
        and build.embedding_model == settings.embedding_model
        and build.embedding_revision == settings.embedding_model_revision
        and (build.quality_report or {}).get("status") == "passed"
        and gates
        and all(bool(value) for value in gates.values())
        and all(config.get(key) == value for key, value in expected.items())
        and bool(config.get("require_native_sparse"))
    )


def _assert_ingestion_build_for_version(
    session,
    release: RagIndexRelease,
    version: DocumentVersion,
) -> None:
    build_id = (release.ingestion_builds or {}).get(version.version_id)
    build = session.get(IngestionBuild, build_id) if build_id else None
    if (
        build is None
        or build.version_id != version.version_id
        or build.source_sha256 != version.sha256
        or not _ingestion_build_matches_runtime(build)
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Release has no approved immutable ingestion build for {version.version_id}.",
        )


def _assert_release_snapshot_eligible(session, release: RagIndexRelease) -> None:
    if release.relationship_snapshot_hash != relationship_snapshot_hash(
        session.query(DocumentRelationship).all()
    ):
        raise HTTPException(
            status_code=409,
            detail="Release legal-relationship snapshot is stale.",
        )
    current_version_ids: set[str] = set()
    for document_id, version_number in release.document_versions.items():
        version = (
            session.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version == int(version_number),
            )
            .one_or_none()
        )
        if version is None or not (
            version.publication_status == "published"
            and version.source_verification_status == "verified"
            and version.legal_review_status == "verified"
            and version.ingestion_status == "completed"
            and version.legal_status in {"active", "amended"}
            and is_canonical_official_source_url(version.source_url)
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Release snapshot is no longer eligible for {document_id}.",
            )
        _assert_ingestion_build_for_version(session, release, version)
        current_version_ids.add(version.version_id)

    for version_id in release.historical_version_ids:
        version = session.get(DocumentVersion, version_id)
        if version is None or not (
            version.publication_status == "published"
            and version.source_verification_status == "verified"
            and version.legal_review_status == "verified"
            and version.ingestion_status == "completed"
            and is_canonical_official_source_url(version.source_url)
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Historical release version is no longer eligible: {version_id}.",
            )
        _assert_ingestion_build_for_version(session, release, version)
        if version.version_id in current_version_ids:
            raise HTTPException(
                status_code=409,
                detail=f"Release version is duplicated as current and historical: {version_id}.",
            )


@router.get("/rag/releases")
def list_rag_releases(session: DbSession, _: AdminUser) -> list[dict]:
    rows = (
        session.query(RagIndexRelease).order_by(RagIndexRelease.created_at.desc()).all()
    )
    return [
        {
            "release_id": row.release_id,
            "namespace": row.namespace,
            "status": row.status,
            "build_status": row.build_status,
            "models": {
                "embedding": row.embedding_model,
                "reranker": row.reranker_model,
                "generator": row.generator_model,
                "verifier": row.verifier_model,
                "prompt": row.prompt_version_id,
            },
            "relationship_snapshot_hash": row.relationship_snapshot_hash,
            "document_versions": row.document_versions,
            "historical_version_ids": row.historical_version_ids,
            "ingestion_builds": row.ingestion_builds,
            "evaluation_metrics": row.evaluation_metrics,
            "retrieval_thresholds": row.retrieval_thresholds,
            "build_summary": row.build_summary,
            "created_at": row.created_at,
            "activated_at": row.activated_at,
        }
        for row in rows
    ]


@router.post("/rag/releases", status_code=status.HTTP_201_CREATED)
def create_rag_release(
    payload: RagIndexReleaseRequest,
    session: DbSession,
    user: AdminUser,
) -> dict:
    if payload.namespace and (
        payload.namespace == settings.pinecone_namespace
        or not payload.namespace.startswith(f"{settings.pinecone_namespace}-")
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{2,159}", payload.namespace) is None
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Release namespace must be a lowercase child namespace of the configured "
                "Pinecone namespace and cannot be the active base namespace."
            ),
        )
    versions = (
        session.query(DocumentVersion)
        .filter(
            DocumentVersion.publication_status == "published",
            DocumentVersion.source_verification_status == "verified",
            DocumentVersion.legal_review_status == "verified",
            DocumentVersion.ingestion_status == "completed",
        )
        .all()
    )
    eligible_pairs: list[tuple[DocumentVersion, IngestionBuild]] = []
    for version in versions:
        build = (
            session.query(IngestionBuild)
            .filter(
                IngestionBuild.version_id == version.version_id,
                IngestionBuild.status == "completed",
                IngestionBuild.review_status == "approved",
                IngestionBuild.embedding_model == settings.embedding_model,
                IngestionBuild.embedding_revision == settings.embedding_model_revision,
            )
            .order_by(
                IngestionBuild.completed_at.desc().nullslast(),
                IngestionBuild.created_at.desc(),
            )
            .first()
        )
        if (
            build is not None
            and is_canonical_official_source_url(version.source_url)
            and _ingestion_build_matches_runtime(build)
        ):
            eligible_pairs.append((version, build))

    candidate_by_document: dict[str, tuple[DocumentVersion, IngestionBuild]] = {}
    for row, build in sorted(
        eligible_pairs,
        key=lambda item: (
            item[0].created_at.timestamp() if item[0].created_at else 0.0,
            item[0].version,
            item[0].version_id,
        ),
        reverse=True,
    ):
        if row.legal_status in {"active", "amended"}:
            candidate_by_document.setdefault(row.document_id, (row, build))
    release_versions = [row for row, _ in candidate_by_document.values()]
    if not release_versions:
        raise HTTPException(
            status_code=409,
            detail=(
                "No version has passed publication, source/legal review, and approved "
                "immutable ingestion-build gates."
            ),
        )
    release_builds = {row.version_id: build.build_id for row, build in eligible_pairs}
    release_id = f"ragrel_{uuid4().hex}"
    namespace = payload.namespace or f"{settings.pinecone_namespace}-{release_id[-12:]}"
    current_version_ids = {candidate.version_id for candidate in release_versions}
    relationship_hash = relationship_snapshot_hash(
        session.query(DocumentRelationship).all()
    )
    release = RagIndexRelease(
        release_id=release_id,
        namespace=namespace,
        status="building",
        build_status="pending",
        embedding_model=settings.embedding_model,
        reranker_model=settings.reranker_model,
        generator_model=settings.groq_model,
        verifier_model=settings.claim_verifier_model,
        prompt_version_id=PROMPT_VERSION_ID,
        relationship_snapshot_hash=relationship_hash,
        document_versions={row.document_id: row.version for row in release_versions},
        historical_version_ids=[
            row.version_id
            for row, _ in eligible_pairs
            if row.version_id not in current_version_ids
        ],
        ingestion_builds=release_builds,
        evaluation_metrics={},
        retrieval_thresholds={"general": 0.08},
        build_summary={},
        created_by=user.user_id,
    )
    session.add(release)
    session.commit()
    return {
        "release_id": release_id,
        "namespace": namespace,
        "status": release.status,
        "build_status": release.build_status,
        "models": {
            "embedding": release.embedding_model,
            "reranker": release.reranker_model,
            "generator": release.generator_model,
            "verifier": release.verifier_model,
            "prompt": release.prompt_version_id,
        },
        "relationship_snapshot_hash": release.relationship_snapshot_hash,
        "document_versions": release.document_versions,
        "historical_version_ids": release.historical_version_ids,
        "ingestion_builds": release.ingestion_builds,
    }


@router.post("/rag/releases/{release_id}/build", status_code=status.HTTP_202_ACCEPTED)
def build_rag_release(
    release_id: str,
    background_tasks: BackgroundTasks,
    session: DbSession,
    _: AdminUser,
) -> dict:
    release = (
        session.query(RagIndexRelease)
        .filter(RagIndexRelease.release_id == release_id)
        .with_for_update()
        .one_or_none()
    )
    if release is None:
        raise HTTPException(status_code=404, detail="RAG index release was not found.")
    if release.status != "building" or release.build_status == "running":
        raise HTTPException(
            status_code=409,
            detail="Only an idle release in the building lifecycle can be built.",
        )
    release.build_status = "queued"
    session.commit()
    try:
        if settings.celery_enabled:
            from app.services.ingestion.tasks import enqueue_index_release

            enqueue_index_release(release_id)
        else:
            from app.services.ingestion.release_builder import build_index_release

            background_tasks.add_task(build_index_release, release_id, storage_root())
    except Exception as exc:
        release.build_status = "failed"
        release.build_summary = {"error": "release_queue_unavailable"}
        session.commit()
        raise HTTPException(
            status_code=503,
            detail="The index build queue is temporarily unavailable.",
        ) from exc
    return {
        "release_id": release_id,
        "namespace": release.namespace,
        "status": "building",
        "build_status": "queued",
    }


@router.post("/rag/releases/{release_id}/transition")
def transition_rag_release(
    release_id: str,
    payload: RagIndexTransitionRequest,
    session: DbSession,
    user: AdminUser,
) -> dict:
    release = (
        session.query(RagIndexRelease)
        .filter(RagIndexRelease.release_id == release_id)
        .with_for_update()
        .one_or_none()
    )
    if release is None:
        raise HTTPException(status_code=404, detail="RAG index release was not found.")
    if payload.action == "validate":
        _assert_release_snapshot_eligible(session, release)
        if release.status != "building" or release.build_status != "succeeded":
            raise HTTPException(
                status_code=409,
                detail="The index release must finish building before validation.",
            )
        if not payload.evaluation_run_id:
            raise HTTPException(
                status_code=422,
                detail="A verified evaluation_run_id is required for validation.",
            )
        evaluation_run = session.get(EvaluationRun, payload.evaluation_run_id)
        if evaluation_run is None:
            raise HTTPException(status_code=404, detail="Evaluation run was not found.")
        if evaluation_run.release_id != release_id:
            raise HTTPException(
                status_code=409,
                detail="Evaluation run does not belong to this immutable index release.",
            )
        evaluation_dataset = session.get(
            EvaluationDataset,
            evaluation_run.dataset_id,
        )
        if (
            evaluation_dataset is None
            or len(evaluation_dataset.questions) < 300
            or {
                question.get("split", "development")
                for question in evaluation_dataset.questions
            }
            != {"development", "test"}
            or any(
                question.get("status") != "verified"
                or question.get("verified_by") in {None, "", "unknown"}
                for question in evaluation_dataset.questions
            )
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Release validation requires at least 300 human-verified questions "
                    "with development and held-out test splits."
                ),
            )
        if len(
            {question.get("question_id") for question in evaluation_dataset.questions}
        ) != len(evaluation_dataset.questions) or len(
            {
                " ".join(str(question.get("question", "")).lower().split())
                for question in evaluation_dataset.questions
            }
        ) != len(evaluation_dataset.questions):
            raise HTTPException(
                status_code=409,
                detail="Release validation requires unique question IDs and texts.",
            )
        covered_scenarios = {
            tag
            for question in evaluation_dataset.questions
            for tag in question.get("scenario_tags", [])
        }
        missing_scenarios = sorted(REQUIRED_RELEASE_SCENARIOS - covered_scenarios)
        if missing_scenarios:
            raise HTTPException(
                status_code=409,
                detail={"missing_release_scenarios": missing_scenarios},
            )
        verified_reviewers = verified_question_reviewers(
            session,
            evaluation_dataset.dataset_id,
        )
        if set(verified_reviewers) != {
            question.get("question_id") for question in evaluation_dataset.questions
        } or any(
            verified_reviewers.get(question.get("question_id"))
            != question.get("verified_by")
            for question in evaluation_dataset.questions
        ):
            raise HTTPException(
                status_code=409,
                detail="Release validation requires a legal-review audit for every question.",
            )
        metrics = evaluation_run.metrics.get("rerank", {})
        missing = [name for name in RELEASE_QUALITY_GATES if name not in metrics]
        if "recommended_refusal_threshold" not in metrics:
            missing.append("recommended_refusal_threshold")
        failed = {
            name: metrics.get(name, 0.0)
            for name, threshold in RELEASE_QUALITY_GATES.items()
            if metrics.get(name, 0.0) < threshold
        }
        if missing or failed:
            raise HTTPException(
                status_code=409,
                detail={"missing_metrics": missing, "failed_gates": failed},
            )
        if (
            metrics.get("unsupported_claim_rate", 1.0) > 0.01
            or metrics.get("stale_source_rate", 1.0) > 0.0
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "failed_gates": {
                        "unsupported_claim_rate": metrics.get("unsupported_claim_rate"),
                        "stale_source_rate": metrics.get("stale_source_rate"),
                    }
                },
            )
        release.evaluation_metrics = metrics
        release.retrieval_thresholds = {
            "general": float(metrics["recommended_refusal_threshold"])
        }
        release.status = "validated"
    elif payload.action == "promote":
        _assert_release_snapshot_eligible(session, release)
        if release.status not in {"validated", "retired"}:
            raise HTTPException(
                status_code=409, detail="Only validated releases can be promoted."
            )
        session.query(RagIndexRelease).with_for_update().all()
        session.query(RagIndexRelease).filter(
            RagIndexRelease.status == "active"
        ).update({RagIndexRelease.status: "retired"})
        session.query(DocumentVersion).filter(
            DocumentVersion.is_current.is_(True)
        ).update({DocumentVersion.is_current: False})
        session.flush()
        for document_id, version_number in release.document_versions.items():
            version_row = (
                session.query(DocumentVersion)
                .filter(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.version == int(version_number),
                )
                .with_for_update()
                .one()
            )
            version_row.is_current = True
        release.status = "active"
        release.activated_at = now_utc()
    else:
        if release.status == "active":
            raise HTTPException(
                status_code=409,
                detail="Promote another validated release before retiring the active release.",
            )
        release.status = "retired"
    session.commit()
    reset_provider_caches()
    log_audit(
        actor=user.user_id,
        action=f"rag_release.{payload.action}",
        target_type="rag_index_release",
        target_id=release_id,
        details={"namespace": release.namespace},
    )
    return {
        "release_id": release.release_id,
        "namespace": release.namespace,
        "status": release.status,
        "evaluation_metrics": release.evaluation_metrics,
        "retrieval_thresholds": release.retrieval_thresholds,
        "activated_at": release.activated_at,
    }


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
    content = await request.body()
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400, detail="The uploaded file is not a valid PDF."
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF file exceeds the 50 MB limit.")

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
        if settings.vector_store == "pinecone":
            response = pinecone_store_from_settings(settings).search(
                payload.question,
                top_k=payload.top_k,
            )
        else:
            engine = RetrievalEngine(
                documents=load_artifact_documents(storage_root()),
                top_k=payload.top_k,
                relationship_index=relationship_index_for_manifest(
                    dataset_metadata_path()
                ),
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
            and metadata.get("regulation_type", "").lower()
            != payload.regulation_type.lower()
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
