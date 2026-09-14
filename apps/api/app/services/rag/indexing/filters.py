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
    """Assemble a backend filter dict; ``None`` when unconstrained."""
    pinecone_filter: dict = {}
    if article:
        pinecone_filter["article"] = {"$eq": article}
    if year:
        pinecone_filter["year"] = {"$eq": year}
    if regulation_type:
        pinecone_filter["regulation_type"] = {"$eq": regulation_type}
    if number:
        pinecone_filter["number"] = {"$eq": number}
    if legal_statuses:
        pinecone_filter["legal_status"] = {"$in": list(legal_statuses)}
    if published_only:
        pinecone_filter["publication_status"] = {"$eq": "published"}
    if effective_on:
        pinecone_filter["effective_date"] = {"$lte": effective_on}
    if segment_kinds:
        pinecone_filter["segment_kind"] = {"$in": list(segment_kinds)}
    if freshness_states:
        pinecone_filter["freshness_state"] = {"$in": list(freshness_states)}
    if topics:
        pinecone_filter["topics_chunk"] = {"$in": list(topics)}
    return pinecone_filter or None
