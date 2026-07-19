from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    prompt_version_id: str
    system_prompt: str
    user_template: str


@dataclass(frozen=True)
class Citation:
    citation_id: str
    chunk_id: str
    document_id: str
    document_title: str
    short_title: str
    legal_status: str
    chapter: str | None
    section: str | None
    article: str | None
    paragraph: str | None
    page_start: int
    page_end: int
    quote: str
    source_url: str
    local_file: str | None
    retrieval_score: float
    rerank_score: float


@dataclass(frozen=True)
class RelatedDocument:
    document_id: str
    title: str
    short_title: str
    legal_status: str
    source_url: str


@dataclass(frozen=True)
class AnswerResponse:
    query: str
    answer: str
    citations: list[Citation]
    confidence: float
    related_documents: list[RelatedDocument]
    refusal_reason: str | None
    clarification_question: str | None
    disclaimer: str
    prompt_version_id: str
    retrieved_chunk_ids: list[str]
    warnings: list[str] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)
