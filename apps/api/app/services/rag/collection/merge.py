"""Conflict resolution between records of the same document.

Curated data and uploads used to merge by silent overwrite. Here every
conflict produces an audit-trailed decision under explicit rules:

1. verified beats unverified;
2. higher source trust wins;
3. newer verification wins;
4. otherwise the current record stands (stability).
"""

from __future__ import annotations

from app.services.rag.collection.schemas import CollectedDocument, MergeDecision
from app.services.rag.collection.sources import SourceRegistry

_VERIFIED = {"verified"}


def _is_verified(document: CollectedDocument) -> bool:
    return document.verification_status in _VERIFIED


def resolve_conflict(
    current: CollectedDocument,
    incoming: CollectedDocument,
    registry: SourceRegistry,
) -> tuple[CollectedDocument, MergeDecision]:
    """Pick the winning record and explain why."""
    if current.sha256 == incoming.sha256:
        decision = MergeDecision(
            document_id=current.document_id,
            winner_origin=current.origin,
            loser_origin=incoming.origin,
            rule="identical_content",
            reason="Same checksum; current record stands.",
        )
        return current, decision
    if _is_verified(current) and not _is_verified(incoming):
        return incoming_loses(current, incoming, "verified_status")
    if _is_verified(incoming) and not _is_verified(current):
        return incoming_wins(current, incoming, "verified_status")
    current_trust = registry.trust_of(current.source_id)
    incoming_trust = registry.trust_of(incoming.source_id)
    if incoming_trust > current_trust:
        return incoming_wins(current, incoming, "source_trust")
    if current_trust > incoming_trust:
        return incoming_loses(current, incoming, "source_trust")
    current_date = current.last_verified_at
    incoming_date = incoming.last_verified_at
    if incoming_date is not None and (current_date is None or incoming_date > current_date):
        return incoming_wins(current, incoming, "newer_verification")
    decision = MergeDecision(
        document_id=current.document_id,
        winner_origin=current.origin,
        loser_origin=incoming.origin,
        rule="stability",
        reason="No decisive signal; current record stands.",
    )
    return current, decision


def incoming_wins(
    current: CollectedDocument, incoming: CollectedDocument, rule: str
) -> tuple[CollectedDocument, MergeDecision]:
    decision = MergeDecision(
        document_id=current.document_id,
        winner_origin=incoming.origin,
        loser_origin=current.origin,
        rule=rule,
        reason=f"Incoming record wins by {rule}.",
    )
    return incoming, decision


def incoming_loses(
    current: CollectedDocument, incoming: CollectedDocument, rule: str
) -> tuple[CollectedDocument, MergeDecision]:
    decision = MergeDecision(
        document_id=current.document_id,
        winner_origin=current.origin,
        loser_origin=incoming.origin,
        rule=rule,
        reason=f"Current record wins by {rule}.",
    )
    return current, decision


def merge_collections(
    base: list[CollectedDocument],
    incoming: list[CollectedDocument],
    registry: SourceRegistry,
) -> tuple[list[CollectedDocument], list[MergeDecision]]:
    """Merge records by id; every content conflict yields a decision."""
    merged = {document.document_id: document for document in base}
    decisions: list[MergeDecision] = []
    for document in incoming:
        if document.document_id not in merged:
            merged[document.document_id] = document
            continue
        winner, decision = resolve_conflict(merged[document.document_id], document, registry)
        merged[document.document_id] = winner
        if decision.rule != "identical_content":
            decisions.append(decision)
    return list(merged.values()), decisions
