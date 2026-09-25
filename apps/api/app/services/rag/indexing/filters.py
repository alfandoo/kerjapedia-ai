"""Query filters: static allowlists plus temporal, kind, and freshness.

Filters narrow candidates server-side before any vector comparison, so
precision and cost improve together. Date comparisons use ISO strings
(``YYYY-MM-DD``), which order lexicographically.
"""

from __future__ import annotations


def build_filter(
    *,
    article: str | None = None,
    year: int | None = None,
    regulation_type: str | None = None,
    number: int | None = None,
    legal_statuses: list[str] | None = None,
    published_only: bool = False,
    effective_on: str | None = None,
    segment_kinds: list[str] | None = None,
    freshness_states: list[str] | None = None,
    topics: list[str] | None = None,
) -> dict | None:
    """Assemble a backend filter dict; ``None`` when unconstrained.

    Production backend is Upstash Vector (HYBRID). The historic
    ``pinecone_filter`` name is retained as a backward-compatible alias in
    tests only; new code should treat the return value as ``vector_filter``.
    """
    vector_filter: dict = {}
    if article:
        vector_filter["article"] = {"$eq": article}
    if year:
        vector_filter["year"] = {"$eq": year}
    if regulation_type:
        vector_filter["regulation_type"] = {"$eq": regulation_type}
    if number:
        vector_filter["number"] = {"$eq": number}
    if legal_statuses:
        vector_filter["legal_status"] = {"$in": list(legal_statuses)}
    if published_only:
        vector_filter["publication_status"] = {"$eq": "published"}
    if effective_on:
        vector_filter["effective_date"] = {"$lte": effective_on}
    if segment_kinds:
        vector_filter["segment_kind"] = {"$in": list(segment_kinds)}
    if freshness_states:
        vector_filter["freshness_state"] = {"$in": list(freshness_states)}
    if topics:
        vector_filter["topics_chunk"] = {"$in": list(topics)}
    return vector_filter or None
