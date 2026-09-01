from __future__ import annotations

from dataclasses import asdict, replace

from app.services.answering.generator import AnswerGenerator, _detect_language
from app.services.evaluation.metrics import (
    citation_correctness,
    faithfulness,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    unsupported_claim_rate,
)
from app.services.evaluation.ragas_metrics import score_ragas_faithfulness
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
        selected = ranked[: max(top_k, 10)]
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
                ragas_faithfulness=None,
                recall_at_10=(
                    recall_at_k(
                        question.expected_document_ids,
                        retrieved_document_ids,
                        10,
                    )
                    if answerable
                    else None
                ),
                ndcg_at_10=(
                    ndcg_at_k(
                        question.expected_document_ids,
                        retrieved_document_ids,
                        10,
                    )
                    if answerable
                    else None
                ),
                unsupported_claim_rate=(unsupported_claim_rate(answer) if answerable else None),
                stale_source_count=sum(
                    item.document.publication_status != "published"
                    or not item.document.is_current
                    or item.document.verification_status != "verified"
                    for item in selected
                ),
                language_correct=(
                    _detect_language(question.question) == _detect_language(answer.answer)
                ),
                best_score=float(best_score),
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
        ragas_faithfulness=_average(item.ragas_faithfulness for item in answerable),
        refusal_accuracy=_average(1.0 if item.refusal_correct else 0.0 for item in results),
        hard_negative_recall_at_5=_average(item.recall_at_5 for item in hard_negatives),
        recall_at_10=_average(item.recall_at_10 for item in answerable),
        ndcg_at_10=_average(item.ndcg_at_10 for item in answerable),
        citation_precision=_average(item.citation_correctness for item in answerable),
        unsupported_claim_rate=_average(item.unsupported_claim_rate for item in answerable),
        stale_source_rate=round(
            sum(item.stale_source_count for item in results)
            / max(1, sum(len(item.retrieved_chunk_ids) for item in results)),
            6,
        ),
        refusal_precision=_safe_ratio(
            sum(
                item.actual_refuse and not expected
                for item, expected in _refusal_pairs(results, questions)
            ),
            sum(item.actual_refuse for item in results),
        ),
        refusal_recall=_safe_ratio(
            sum(
                item.actual_refuse and not expected
                for item, expected in _refusal_pairs(results, questions)
            ),
            sum(question.should_refuse for question in questions),
        ),
        language_accuracy=_average(1.0 if item.language_correct else 0.0 for item in results),
        recommended_refusal_threshold=_calibrate_refusal_threshold(results, questions),
    )


def _average(values) -> float:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 6) if present else 0.0


def _refusal_pairs(
    results: list[QuestionEvaluation],
    questions: list[EvaluationQuestion],
) -> list[tuple[QuestionEvaluation, bool]]:
    expected_answerable = {
        question.question_id: not question.should_refuse for question in questions
    }
    return [(result, expected_answerable.get(result.question_id, True)) for result in results]


def _safe_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _calibrate_refusal_threshold(
    results: list[QuestionEvaluation],
    questions: list[EvaluationQuestion],
) -> float:
    expected_refusal = {question.question_id: question.should_refuse for question in questions}
    candidates = sorted({0.0, *[result.best_score for result in results], 1.0})
    best_threshold = 0.08
    best_accuracy = -1.0
    for threshold in candidates:
        correct = sum(
            (result.best_score < threshold) == expected_refusal.get(result.question_id, False)
            for result in results
        )
        accuracy = correct / max(1, len(results))
        if accuracy > best_accuracy or (accuracy == best_accuracy and threshold > best_threshold):
            best_accuracy = accuracy
            best_threshold = threshold
    return round(best_threshold, 6)


def run_provider_evaluation(
    questions: list[EvaluationQuestion],
    retriever,
    generator,
    top_k: int = 10,
    ragas_scorer=None,
) -> dict:
    development = [question for question in questions if question.split == "development"]
    held_out = [question for question in questions if question.split == "test"]
    if not development or not held_out:
        raise ValueError("Provider evaluation requires development and held-out test splits.")

    development_results = _evaluate_provider_questions(
        development,
        retriever,
        generator,
        top_k,
        threshold=_REFUSAL_THRESHOLDS["rerank"],
        ragas_scorer=ragas_scorer,
    )
    development_metrics = _aggregate(development_results, development)
    calibrated_threshold = development_metrics.recommended_refusal_threshold
    test_results = _evaluate_provider_questions(
        held_out,
        retriever,
        generator,
        top_k,
        threshold=calibrated_threshold,
        ragas_scorer=ragas_scorer,
    )
    test_metrics = replace(
        _aggregate(test_results, held_out),
        recommended_refusal_threshold=calibrated_threshold,
    )
    per_topic = {
        category: _aggregate(
            [result for result in test_results if result.category == category],
            [question for question in held_out if question.category == category],
        )
        for category in sorted({question.category for question in held_out})
    }
    experiment = {
        "mode": "rerank",
        "metrics": asdict(test_metrics),
        "development_metrics": asdict(development_metrics),
        "per_topic": {key: asdict(value) for key, value in per_topic.items()},
        "results": [asdict(result) for result in test_results],
    }
    return {
        "question_count": len(questions),
        "development_count": len(development),
        "held_out_count": len(held_out),
        "top_k": top_k,
        "experiments": [experiment],
    }


def _evaluate_provider_questions(
    questions: list[EvaluationQuestion],
    retriever,
    generator,
    top_k: int,
    threshold: float,
    ragas_scorer=None,
) -> list[QuestionEvaluation]:
    results: list[QuestionEvaluation] = []
    for question in questions:
        retrieval = retriever.search(
            question.question,
            top_k=max(10, top_k),
            min_final_score=0.0,
        )
        selected = retrieval.results[: max(top_k, 10)]
        best_score = selected[0].final_score if selected else 0.0
        actual_refuse = retrieval.should_refuse or not selected or best_score < threshold
        evaluated_retrieval = RetrievalResponse(
            query=retrieval.query,
            results=selected,
            warnings=retrieval.warnings,
            should_refuse=actual_refuse,
            refusal_reason=(
                retrieval.refusal_reason
                if retrieval.should_refuse
                else "no_retrieved_chunk_passed_calibrated_score"
                if actual_refuse
                else None
            ),
        )
        answer = generator.generate(question.question, evaluated_retrieval)
        retrieved_document_ids = [item.document.document_id for item in selected]
        answerable = not question.should_refuse
        results.append(
            QuestionEvaluation(
                question_id=question.question_id,
                category=question.category,
                mode="rerank",
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
                ragas_faithfulness=(
                    score_ragas_faithfulness(
                        ragas_scorer,
                        question=question.question,
                        response=answer.answer,
                        contexts=[item.document.text for item in selected],
                    )
                    if answerable and ragas_scorer is not None
                    else None
                ),
                recall_at_10=(
                    recall_at_k(question.expected_document_ids, retrieved_document_ids, 10)
                    if answerable
                    else None
                ),
                ndcg_at_10=(
                    ndcg_at_k(question.expected_document_ids, retrieved_document_ids, 10)
                    if answerable
                    else None
                ),
                unsupported_claim_rate=(unsupported_claim_rate(answer) if answerable else None),
                stale_source_count=sum(
                    item.document.publication_status != "published"
                    or not item.document.is_current
                    or item.document.verification_status != "verified"
                    for item in selected
                ),
                language_correct=(
                    _detect_language(question.question) == _detect_language(answer.answer)
                ),
                best_score=float(best_score),
                refusal_correct=actual_refuse == question.should_refuse,
                actual_refuse=actual_refuse,
                retrieved_document_ids=retrieved_document_ids,
                retrieved_chunk_ids=[item.document.chunk_id for item in selected],
                warnings=retrieval.warnings,
            )
        )
    return results
