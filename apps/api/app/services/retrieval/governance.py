from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.ingestion import DocumentRelationship, DocumentVersion, RagIndexRelease
from app.services.ingestion.governance import is_canonical_official_source_url
from app.services.retrieval.relationships import (
    RelationshipIndex,
    relationship_index_from_rows,
    relationship_snapshot_hash,
)


@dataclass(frozen=True)
class RetrievalGovernance:
    eligible_versions: dict[str, int]
    eligible_builds: dict[str, str]
    relationship_index: RelationshipIndex
    active_release_id: str | None
    active_namespace: str | None
    active_models: dict[str, str]
    min_final_score: float
    release_consistent: bool


def load_retrieval_governance(
    session: Session,
    *,
    allow_unpublished: bool,
) -> RetrievalGovernance:
    versions_query = session.query(DocumentVersion).filter(
        DocumentVersion.is_current.is_(True)
    )
    if not allow_unpublished:
        versions_query = versions_query.filter(
            DocumentVersion.publication_status == "published",
            DocumentVersion.source_verification_status == "verified",
            DocumentVersion.legal_review_status == "verified",
            DocumentVersion.ingestion_status == "completed",
            DocumentVersion.legal_status.in_(("active", "amended")),
        )
    versions = versions_query.all()
    if not allow_unpublished:
        versions = [
            row for row in versions if is_canonical_official_source_url(row.source_url)
        ]
    active_release = (
        session.query(RagIndexRelease)
        .filter(RagIndexRelease.status == "active")
        .order_by(RagIndexRelease.activated_at.desc())
        .first()
    )
    eligible_versions = {row.document_id: row.version for row in versions}
    active_snapshot = (
        {key: int(value) for key, value in active_release.document_versions.items()}
        if active_release
        else {}
    )
    historical_consistent = True
    if active_release and active_release.historical_version_ids:
        historical_rows = (
            session.query(DocumentVersion)
            .filter(
                DocumentVersion.version_id.in_(active_release.historical_version_ids)
            )
            .all()
        )
        historical_consistent = len(historical_rows) == len(
            set(active_release.historical_version_ids)
        ) and all(
            row.publication_status == "published"
            and row.source_verification_status == "verified"
            and row.legal_review_status == "verified"
            and row.ingestion_status == "completed"
            and is_canonical_official_source_url(row.source_url)
            for row in historical_rows
        )
    relationship_rows = session.query(DocumentRelationship).all()
    relationships_consistent = (
        active_release is None
        or active_release.relationship_snapshot_hash
        == relationship_snapshot_hash(relationship_rows)
    )
    return RetrievalGovernance(
        eligible_versions=eligible_versions,
        eligible_builds=(
            dict(active_release.ingestion_builds or {}) if active_release else {}
        ),
        relationship_index=relationship_index_from_rows(relationship_rows),
        active_release_id=active_release.release_id if active_release else None,
        active_namespace=active_release.namespace if active_release else None,
        active_models=(
            {
                "embedding": active_release.embedding_model,
                "reranker": active_release.reranker_model,
                "generator": active_release.generator_model,
                "verifier": active_release.verifier_model,
                "prompt": active_release.prompt_version_id,
            }
            if active_release
            else {}
        ),
        min_final_score=float(
            (active_release.retrieval_thresholds if active_release else {}).get(
                "general", 0.08
            )
        ),
        release_consistent=(
            True
            if allow_unpublished or active_release is None
            else (
                active_snapshot == eligible_versions
                and historical_consistent
                and relationships_consistent
                and all(
                    version_id in (active_release.ingestion_builds or {})
                    for version_id in {row.version_id for row in versions}
                )
            )
        ),
    )
