from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    status: str
    service: str
    version: str
    providers: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=256)


class UserResponse(ApiModel):
    user_id: str
    email: str
    name: str
    roles: list[str]


class LoginResponse(ApiModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(ApiModel):
    refresh_token: str = Field(min_length=10, max_length=1000)


class MessageResponse(ApiModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AskRequest(ApiModel):
    question: str = Field(min_length=4, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=80)
    top_k: int = Field(default=5, ge=1, le=10)


class AskResponse(ApiModel):
    conversation_id: str
    answer: dict[str, Any]
    latency_ms: int
    retrieval_score: float | None
    token_usage: dict[str, int]


class ConversationSummary(ApiModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetail(ApiModel):
    conversation_id: str
    title: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime


class ConversationUpdateRequest(ApiModel):
    title: str = Field(min_length=1, max_length=80)


class DocumentSummary(ApiModel):
    document_id: str
    title: str
    short_title: str
    regulation_type: str
    number: int
    year: int
    legal_status: str
    topics: list[str]
    source_url: str
    pdf_url: str


class DocumentUpdateRequest(ApiModel):
    legal_status: str | None = Field(default=None, max_length=80)
    topics: list[str] | None = None
    verification_status: str | None = Field(default=None, max_length=80)


class DocumentRelationshipRequest(ApiModel):
    to_document_id: str = Field(min_length=3, max_length=80)
    relationship_type: Literal["amended_by", "implements", "implemented_by", "related_to"]
    confidence: Literal["low", "medium", "high"] = "medium"
    notes: str | None = Field(default=None, max_length=1000)


class PublicationRequest(ApiModel):
    action: Literal["publish", "unpublish"]


class RetrievalPlaygroundRequest(ApiModel):
    question: str = Field(min_length=4, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class IngestionJobRequest(ApiModel):
    document_id: str = Field(min_length=3, max_length=80)
    persist_db: bool = False


class FeedbackRequest(ApiModel):
    question: str = Field(min_length=4, max_length=2000)
    answer_id: str | None = Field(default=None, max_length=120)
    rating: Literal["helpful", "not_helpful"]
    issue_category: str | None = Field(default=None, max_length=80)
    comment: str | None = Field(default=None, max_length=1000)


class EvaluationQuestionInput(ApiModel):
    question_id: str = Field(min_length=5, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    question: str = Field(min_length=4, max_length=2000)
    expected_answer: str = Field(min_length=4, max_length=4000)
    expected_document_ids: list[str]
    expected_articles: list[str]
    expected_topics: list[str]
    should_refuse: bool = False
    hard_negative: bool = False
    verified_by: str = Field(default="unknown", max_length=120)
    status: str = Field(default="needs_human_review", max_length=80)


class EvaluationDatasetRequest(ApiModel):
    name: str = Field(min_length=3, max_length=120)
    questions: list[EvaluationQuestionInput] = Field(min_length=1, max_length=500)


class EvaluationRunRequest(ApiModel):
    dataset_id: str = Field(min_length=3, max_length=120)
    top_k: int = Field(default=5, ge=1, le=10)
    experiment_modes: list[Literal["baseline", "dense", "hybrid", "rerank"]] = Field(
        default_factory=lambda: ["baseline", "dense", "hybrid", "rerank"]
    )
