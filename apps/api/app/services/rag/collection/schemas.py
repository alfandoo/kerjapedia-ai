"""Shared records for the collection stage.

All records are immutable: history (checksums, decisions) is append-only,
state changes produce new records. Nothing is silently overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceRecord:
    """A registered origin of documents (curated set, admin upload, crawler)."""

    source_id: str
    name: str
    base_url: str = ""
    allowed_domains: tuple[str, ...] = ()
    trust_score: float = 0.5
    enabled: bool = True


@dataclass(frozen=True)
class ChecksumEvent:
    """One observation of a document's bytes. History, never edited."""

    sha256: str
    size_bytes: int
    collected_at: datetime
    origin: str  # curated | upload | connector


@dataclass(frozen=True)
class TopicAssignment:
    """A topic label plus how much it may be trusted.

    Only ``verified`` assignments may feed retrieval signals.
    """

    topic: str
    confidence: str = "low"  # high | medium | low
    verified: bool = False
    verified_by: str | None = None


@dataclass(frozen=True)
class CollectedDocument:
    """A document as known by the collection stage."""

    document_id: str
    title: str
    regulation_type: str = ""
    number: int = 0
    year: int = 0
    issuer: str = ""
    topics: tuple[TopicAssignment, ...] = ()
    legal_status: str = "needs_verification"
    verification_status: str = "pending"
    source_id: str = ""
    source_url: str = ""
    local_file: str = ""
    file_name: str = ""
    size_bytes: int = 0
    sha256: str = ""
    checksum_history: tuple[ChecksumEvent, ...] = ()
    collected_at: datetime | None = None
    last_verified_at: datetime | None = None
    origin: str = "curated"  # curated | upload | connector
    page_count: int = 0
    language: str = ""


@dataclass(frozen=True)
class EligibilityIssue:
    """One reason a file may not enter the pipeline."""

    code: str
    message: str
    fatal: bool = True


@dataclass(frozen=True)
class EligibilityVerdict:
    """Eligibility never crashes the pipeline: unfit files are quarantined
    with reasons instead."""

    eligible: bool
    issues: tuple[EligibilityIssue, ...] = ()
    quarantined: bool = False


@dataclass(frozen=True)
class MergeDecision:
    """Audit trail for one conflict between two records of a document."""

    document_id: str
    winner_origin: str
    loser_origin: str
    rule: str
    reason: str


@dataclass(frozen=True)
class FreshnessStatus:
    """How much the verification of a document can still be trusted."""

    state: str  # fresh | due | stale
    days_since_verification: int | None = None
    action: str = "none"
