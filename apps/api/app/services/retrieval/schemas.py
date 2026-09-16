from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QueryUnderstanding:
    original_query: str
    normalized_query: str
    rewritten_queries: list[str]
    detected_topics: list[str]
    detected_intents: list[str]
    filters: dict[str, Any]
    retrieval_query: str = ""
    normalized_retrieval_query: str = ""
    context_topics: list[str] = field(default_factory=list)
    context_document_ids: list[str] = field(default_factory=list)
    context_articles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalDocument:
    chunk_id: str
    document_id: str
    text: str
    chapter: str | None
    section: str | None
    article: str | None
    paragraph: str | None
    page_start: int
    page_end: int
    token_count: int
    topics: list[str]
    legal_status: str
    source_url: str
    retrieval_text: str | None = None
    build_id: str | None = None
    embedding_model: str | None = None
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    document_version: int | None = None
    publication_status: str = "published"
    verification_status: str = "verified"
    is_current: bool = True
    parent_text: str | None = None
    char_start: int = 0
    char_end: int = 0


@dataclass(frozen=True)
class RankedChunk:
    document: RetrievalDocument
    lexical_score: float
    semantic_score: float
    fusion_score: float
    rerank_score: float
    final_score: float
    match_reasons: list[str]


@dataclass(frozen=True)
class RetrievalResponse:
    query: QueryUnderstanding
    results: list[RankedChunk]
    warnings: list[str]
    should_refuse: bool
    refusal_reason: str | None
    index_release_id: str | None = None
    index_namespace: str | None = None
    active_release_id: str | None = None
    timing: dict[str, float] = field(default_factory=dict)
    context_metrics: dict[str, int] = field(default_factory=dict)
