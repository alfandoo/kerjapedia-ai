from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ExperimentMode = Literal["baseline", "dense", "hybrid", "rerank"]


@dataclass(frozen=True)
class EvaluationQuestion:
    question_id: str
    category: str
    question: str
    expected_answer: str
    expected_document_ids: list[str]
    expected_articles: list[str]
    expected_topics: list[str]
    should_refuse: bool
    hard_negative: bool = False
    verified_by: str = "unknown"
    status: str = "needs_human_review"

    @classmethod
    def from_dict(cls, data: dict) -> EvaluationQuestion:
        return cls(
            question_id=data["question_id"],
            category=data["category"],
            question=data["question"],
            expected_answer=data["expected_answer"],
            expected_document_ids=list(data["expected_document_ids"]),
            expected_articles=list(data["expected_articles"]),
            expected_topics=list(data["expected_topics"]),
            should_refuse=bool(data["should_refuse"]),
            hard_negative=bool(data.get("hard_negative", False)),
            verified_by=data.get("verified_by", "unknown"),
            status=data.get("status", "needs_human_review"),
        )


@dataclass(frozen=True)
class QuestionEvaluation:
    question_id: str
    category: str
    mode: ExperimentMode
    recall_at_5: float | None
    reciprocal_rank: float | None
    citation_correctness: float | None
    faithfulness: float | None
    refusal_correct: bool
    actual_refuse: bool
    retrieved_document_ids: list[str]
    retrieved_chunk_ids: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AggregateMetrics:
    question_count: int
    answerable_count: int
    refusal_count: int
    recall_at_5: float
    mean_reciprocal_rank: float
    citation_correctness: float
    faithfulness: float
    refusal_accuracy: float
    hard_negative_recall_at_5: float


@dataclass(frozen=True)
class ExperimentReport:
    mode: ExperimentMode
    metrics: AggregateMetrics
    per_topic: dict[str, AggregateMetrics]
    results: list[QuestionEvaluation]
