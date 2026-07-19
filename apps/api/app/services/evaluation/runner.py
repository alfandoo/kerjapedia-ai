from __future__ import annotations

from dataclasses import asdict

from app.services.answering.generator import AnswerGenerator
from app.services.evaluation.metrics import (
    citation_correctness,
    faithfulness,
    recall_at_k,
    reciprocal_rank,
)
from app.services.evaluation.schemas import (
    AggregateMetrics,
    EvaluationQuestion,
    ExperimentMode,
    ExperimentReport,
    QuestionEvaluation,
)
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument, RetrievalResponse

EXPERIMENT_MODES: tuple[ExperimentMode, ...] = ("baseline", "dense", "hybrid", "rerank")
_MODE_SCORE = {
    "baseline": "lexical_score",
    "dense": "semantic_score",
    "hybrid": "fusion_score",
    "rerank": "final_score",
}
_REFUSAL_THRESHOLDS = {
    "baseline": 0.01,
    "dense": 0.05,
    "hybrid": 0.005,
    "rerank": 0.08,
}


def run_experiments(
    questions: list[EvaluationQuestion],
    documents: list[RetrievalDocument],
    modes: list[ExperimentMode] | tuple[ExperimentMode, ...] = EXPERIMENT_MODES,
    top_k: int = 5,
) -> dict:
    reports = [run_experiment(questions, documents, mode, top_k) for mode in modes]
    return {
        "question_count": len(questions),
        "top_k": top_k,
        "experiments": [asdict(report) for report in reports],
    }


def run_experiment(
    questions: list[EvaluationQuestion],
    documents: list[RetrievalDocument],
    mode: ExperimentMode,
    top_k: int = 5,
) -> ExperimentReport:
    if mode not in EXPERIMENT_MODES:
        raise ValueError(f"Unsupported experiment mode: {mode}")
    engine = RetrievalEngine(documents=documents, top_k=max(top_k, len(documents)))
    generator = AnswerGenerator()
    results: list[QuestionEvaluation] = []

    for question in questions:
        retrieval = engine.search(question.question, top_k=max(top_k, len(documents)))
        ranked = _rank(retrieval.results, mode)
        selected = ranked[:top_k]
        score_name = _MODE_SCORE[mode]
        best_score = getattr(selected[0], score_name) if selected else 0.0
        actual_refuse = not selected or best_score < _REFUSAL_THRESHOLDS[mode]
        mode_retrieval = RetrievalResponse(
            query=retrieval.query,
            results=selected,
            warnings=retrieval.warnings,
            should_refuse=actual_refuse,
            refusal_reason=("no_retrieved_chunk_passed_minimum_score" if actual_refuse else None),
        )
        answer = generator.generate(question.question, mode_retrieval)
        retrieved_document_ids = [item.document.document_id for item in selected]
        answerable = not question.should_refuse
        results.append(
            QuestionEvaluation(
                question_id=question.question_id,
                category=question.category,
                mode=mode,
                recall_at_5=(
                    recall_at_k(question.expected_document_ids, retrieved_document_ids, 5)
                    if answerable
                    else None
                ),
                reciprocal_rank=(
                    reciprocal_rank(question.expected_document_ids, retrieved_document_ids)
                    if answerable
                    else None
                ),
                citation_correctness=(
                    citation_correctness(
                        answer,
                        question.expected_document_ids,
                        question.expected_articles,
                    )
                    if answerable
                    else None
                ),
                faithfulness=faithfulness(answer) if answerable else None,
                refusal_correct=actual_refuse == question.should_refuse,
                actual_refuse=actual_refuse,
                retrieved_document_ids=retrieved_document_ids,
                retrieved_chunk_ids=[item.document.chunk_id for item in selected],
                warnings=retrieval.warnings,
            )
        )

    per_topic = {
        category: _aggregate(
            [result for result in results if result.category == category],
            [question for question in questions if question.category == category],
        )
        for category in sorted({question.category for question in questions})
    }
    return ExperimentReport(
        mode=mode,
        metrics=_aggregate(results, questions),
        per_topic=per_topic,
        results=results,
    )


def _rank(results: list[RankedChunk], mode: ExperimentMode) -> list[RankedChunk]:
    score_name = _MODE_SCORE[mode]
    return sorted(results, key=lambda item: getattr(item, score_name), reverse=True)


def _aggregate(
    results: list[QuestionEvaluation],
    questions: list[EvaluationQuestion],
) -> AggregateMetrics:
    answerable = [result for result in results if result.recall_at_5 is not None]
    hard_negative_ids = {question.question_id for question in questions if question.hard_negative}
    hard_negatives = [
        result
        for result in answerable
        if result.question_id in hard_negative_ids and result.recall_at_5 is not None
    ]
    return AggregateMetrics(
        question_count=len(results),
        answerable_count=len(answerable),
        refusal_count=len(results) - len(answerable),
        recall_at_5=_average(item.recall_at_5 for item in answerable),
        mean_reciprocal_rank=_average(item.reciprocal_rank for item in answerable),
        citation_correctness=_average(item.citation_correctness for item in answerable),
        faithfulness=_average(item.faithfulness for item in answerable),
        refusal_accuracy=_average(1.0 if item.refusal_correct else 0.0 for item in results),
        hard_negative_recall_at_5=_average(item.recall_at_5 for item in hard_negatives),
    )


def _average(values) -> float:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 6) if present else 0.0
