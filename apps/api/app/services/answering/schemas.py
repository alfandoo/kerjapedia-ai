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
    document_version: int | None = None


@dataclass(frozen=True)
class GroundedClaim:
    text: str
    cited_chunk_ids: list[str]
    supported: bool
    support_score: float


@dataclass(frozen=True)
class RelatedDocument:
    document_id: str
    title: str
    short_title: str
    legal_status: str
    source_url: str


@dataclass(frozen=True)
class HistoryTurn:
    """One prior answered turn, redacted at build time, passed to the LLM
    so follow-up questions resolve against visible conversation context."""

    question: str
    answer: str


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
    claims: list[GroundedClaim] = field(default_factory=list)
    trace_id: str | None = None
    answer_status: str = "answered"
    answer_version: str = "grounded-verified-answer-v3"
