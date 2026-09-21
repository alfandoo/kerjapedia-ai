from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ExperimentMode = Literal["baseline", "dense", "hybrid", "rerank", "upstash"]


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
    split: Literal["development", "test"] = "development"
    scenario_tags: list[str] = field(default_factory=list)

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
            split=data.get("split", "development"),
            scenario_tags=list(data.get("scenario_tags", [])),
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
    answer_correctness: float | None
    ragas_faithfulness: float | None
    recall_at_10: float | None
    ndcg_at_10: float | None
    unsupported_claim_rate: float | None
    stale_source_count: int
    language_correct: bool
    best_score: float
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
    answer_correctness: float
    ragas_faithfulness: float
    refusal_accuracy: float
    hard_negative_recall_at_5: float
    recall_at_10: float
    ndcg_at_10: float
    citation_precision: float
    unsupported_claim_rate: float
    stale_source_rate: float
    refusal_precision: float
    refusal_recall: float
    language_accuracy: float
    recommended_refusal_threshold: float


@dataclass(frozen=True)
class ExperimentReport:
    mode: ExperimentMode
    metrics: AggregateMetrics
    per_topic: dict[str, AggregateMetrics]
    results: list[QuestionEvaluation]
