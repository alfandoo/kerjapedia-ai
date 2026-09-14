"""Document collection: registry, collection, topics, merge, freshness."""

from app.services.rag.collection.collector import (
    check_eligibility,
    collect_document,
    register_checksum,
)
from app.services.rag.collection.freshness import evaluate_freshness
from app.services.rag.collection.merge import merge_collections, resolve_conflict
from app.services.rag.collection.schemas import (
    ChecksumEvent,
    CollectedDocument,
    EligibilityIssue,
    EligibilityVerdict,
    FreshnessStatus,
    MergeDecision,
    SourceRecord,
    TopicAssignment,
)
from app.services.rag.collection.sources import (
    Connector,
    FetchedFile,
    SourceRegistry,
)
from app.services.rag.collection.topics import (
    retrieval_topics,
    suggest_topics,
    verify_topics,
)

__all__ = [
    "ChecksumEvent",
    "CollectedDocument",
    "Connector",
    "EligibilityIssue",
    "EligibilityVerdict",
    "FetchedFile",
    "FreshnessStatus",
    "MergeDecision",
    "SourceRecord",
    "TopicAssignment",
    "check_eligibility",
    "collect_document",
    "evaluate_freshness",
    "merge_collections",
    "register_checksum",
    "resolve_conflict",
    "retrieval_topics",
    "suggest_topics",
    "verify_topics",
    "SourceRegistry",
]
