"""Index records: vectors, manifests, and clearance receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class StoredVector:
    """One vector plus its metadata, backend-agnostic."""

    id: str
    values: tuple[float, ...]
    sparse: dict[int, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WriteReport:
    """Outcome of a verified write: counts, worst sample cosine, rollback."""

    upserted: int = 0
    verified: int = 0
    worst_cosine: float = 0.0
    rolled_back: bool = False


@dataclass(frozen=True)
class ReleaseManifest:
    """Standalone receipt of what fills a namespace: index, build, model
    space, counts, and who/when. Travels with the index, not just the DB."""

    index_name: str
    namespace: str
    build_id: str
    model_space: str
    vector_count: int
    document_ids: tuple[str, ...] = ()
    created_at: datetime | None = None
    created_by: str = ""


@dataclass(frozen=True)
class NamespaceClearance:
    """Receipt of a namespace deletion: preview or confirmed with backup."""

    namespace: str
    vector_count: int = 0
    sample_ids: tuple[str, ...] = ()
    backed_up_ids: tuple[str, ...] = ()
    confirmed: bool = False
