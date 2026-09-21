from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace

from app.services.answering.generator import AnswerGenerator, _detect_language
from app.services.evaluation.metrics import (
    answer_correctness,
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
from app.services.retrieval.reranker import DEFAULT_RERANK_WEIGHTS, RerankWeights
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument, RetrievalResponse

EXPERIMENT_MODES: tuple[ExperimentMode, ...] = ("baseline", "dense", "hybrid", "rerank", "upstash")
UPSTASH_RANKING_MODES: tuple[ExperimentMode, ...] = (
    "baseline",
    "dense",
    "hybrid",
    "rerank",
)
_MODE_SCORE = {
    "baseline": "lexical_score",
    "dense": "semantic_score",
    "hybrid": "fusion_score",
    "rerank": "final_score",
    "upstash": "final_score",
}
_REFUSAL_THRESHOLDS = {
    "baseline": 0.01,
    "dense": 0.05,
    "hybrid": 0.005,
    "rerank": 0.08,
    "upstash": 0.0,
}


def _upstash_search(query: str, top_k: int) -> RetrievalResponse:
    """Live retrieval against the Upstash HYBRID index (hosted embeddings).

    Pure ranking measurement: no minimum-score gate, so an empty candidate
    set is the only refusal. Missing credentials raise an actionable error
    that surfaces as the run failure message.
    """
    from app.core.config import settings
    from app.services.providers import upstash_vector_store_from_settings

    if not settings.upstash_vector_url or not settings.upstash_vector_token:
        raise RuntimeError(
            "Upstash evaluation needs UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN."
        )
    store = upstash_vector_store_from_settings(settings)
    return store.search(query, top_k=max(top_k, 10), min_final_score=0.0)


def _upstash_candidate_search(query: str) -> RetrievalResponse:
    """Return the scored live candidate pool before MMR/final selection."""
    from app.core.config import settings
    from app.services.providers import upstash_vector_store_from_settings

    if not settings.upstash_vector_url or not settings.upstash_vector_token:
        raise RuntimeError("Upstash evaluation needs UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN.")
    store = upstash_vector_store_from_settings(settings)
    return store.search_candidates(query)


ProgressCallback = Callable[[int, int], None]
"""Called as ``callback(completed, total)`` after each evaluated question."""


def run_experiments(
    questions: list[EvaluationQuestion],
    documents: list[RetrievalDocument],
    modes: list[ExperimentMode] | tuple[ExperimentMode, ...] = UPSTASH_RANKING_MODES,
    top_k: int = 5,
    on_progress: ProgressCallback | None = None,
) -> dict:
    selected_modes = tuple(modes)
    if "upstash" in selected_modes:
        if selected_modes != ("upstash",):
            raise ValueError("Upstash live evaluation cannot be mixed with artifact modes.")
        searches = [_upstash_candidate_search(question.question) for question in questions]
        total = len(questions) * len(UPSTASH_RANKING_MODES)
        reports = []
        for mode_index, mode in enumerate(UPSTASH_RANKING_MODES):
            base = mode_index * len(questions)

            def report_mode(completed: int, _total: int, _base: int = base) -> None:
                if on_progress is not None:
                    on_progress(_base + completed, total)

            reports.append(_evaluate_searches(questions, searches, mode, top_k, report_mode))
        return {
            "question_count": len(questions),
            "top_k": top_k,
            "experiments": [asdict(report) for report in reports],
        }

    total = len(questions) * len(modes)
    reports = []
    for mode_index, mode in enumerate(modes):
        base = mode_index * len(questions)

        def report_mode(completed: int, _total: int, _base: int = base) -> None:
            if on_progress is not None:
                on_progress(_base + completed, total)

        reports.append(run_experiment(questions, documents, mode, top_k, report_mode))
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
    on_progress: ProgressCallback | None = None,
) -> ExperimentReport:
    if mode not in EXPERIMENT_MODES:
        raise ValueError(f"Unsupported experiment mode: {mode}")
    if mode == "upstash":
        searches = [_upstash_search(question.question, top_k) for question in questions]
    else:
        engine = RetrievalEngine(documents=documents, top_k=max(top_k, len(documents)))
        searches = [
            engine.search(question.question, top_k=max(top_k, len(documents)))
            for question in questions
        ]
    return _evaluate_searches(questions, searches, mode, top_k, on_progress)


def _evaluate_searches(
    questions: list[EvaluationQuestion],
    searches: list[RetrievalResponse],
    mode: ExperimentMode,
    top_k: int,
    on_progress: ProgressCallback | None = None,
) -> ExperimentReport:
    generator = AnswerGenerator()
    results: list[QuestionEvaluation] = []

    for index, (question, retrieval) in enumerate(zip(questions, searches, strict=True)):
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
        retrieved_document_ids = _unique_document_ids(selected)
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
                answer_correctness=(
                    answer_correctness(answer, question.expected_answer)
                    if answerable
                    else None
                ),
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
        if on_progress is not None:
            on_progress(index + 1, len(questions))

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


DEFAULT_WEIGHT_SWEEP: tuple[tuple[str, RerankWeights], ...] = (
    ("baseline", DEFAULT_RERANK_WEIGHTS),
    (
        "semantic_heavy",
        RerankWeights(fusion=0.35, lexical=0.15, semantic=0.35, overlap=0.15),
    ),
    (
        "lexical_heavy",
        RerankWeights(fusion=0.35, lexical=0.35, semantic=0.15, overlap=0.15),
    ),
    (
        "fusion_heavy",
        RerankWeights(fusion=0.60, lexical=0.15, semantic=0.15, overlap=0.10),
    ),
    (
        "overlap_heavy",
        RerankWeights(fusion=0.35, lexical=0.20, semantic=0.20, overlap=0.25),
    ),
)


def sweep_rerank_weights(
    questions: list[EvaluationQuestion],
    documents: list[RetrievalDocument],
    weight_options: list[tuple[str, RerankWeights]]
    | tuple[tuple[str, RerankWeights], ...]
    | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Compare rerank weight configs on retrieval quality (no answer generation).

    Each option is evaluated with mean recall@k and mean reciprocal rank over
    answerable questions, mirroring the retrieval slice used in run_experiment.
    Returns rows sorted by recall then reciprocal rank, so the winning config
    can be recorded as the calibrated `RerankWeights` for production.
    """
    options = list(weight_options) if weight_options is not None else list(DEFAULT_WEIGHT_SWEEP)
    rows: list[dict] = []
    for name, weights in options:
        engine = RetrievalEngine(
            documents=documents,
            top_k=max(top_k, len(documents)),
            rerank_weights=weights,
        )
        recalls: list[float] = []
        ranks: list[float] = []
        for question in questions:
            if question.should_refuse:
                continue
            retrieval = engine.search(question.question, top_k=max(top_k, len(documents)))
            retrieved_ids = [
                item.document.document_id for item in retrieval.results[: max(top_k, 10)]
            ]
            recalls.append(recall_at_k(question.expected_document_ids, retrieved_ids, top_k))
            ranks.append(reciprocal_rank(question.expected_document_ids, retrieved_ids))
        rows.append(
            {
                "name": name,
                "weights": asdict(weights),
                "evaluated": len(recalls),
                "mean_recall_at_k": (sum(recalls) / len(recalls)) if recalls else 0.0,
                "mean_reciprocal_rank": (sum(ranks) / len(ranks)) if ranks else 0.0,
            }
        )
    rows.sort(key=lambda row: (row["mean_recall_at_k"], row["mean_reciprocal_rank"]), reverse=True)
    return rows


def _rank(results: list[RankedChunk], mode: ExperimentMode) -> list[RankedChunk]:
    score_name = _MODE_SCORE[mode]
    return sorted(results, key=lambda item: getattr(item, score_name), reverse=True)


def _unique_document_ids(selected: list[RankedChunk]) -> list[str]:
    """Rank positions for metrics count a document once: several chunks of
    the same regulation must not inflate NDCG the way raw chunk lists do."""
    return list(dict.fromkeys(item.document.document_id for item in selected))


def evaluate_retrieval_modes(
    questions: list[EvaluationQuestion],
    documents: list[RetrievalDocument],
    modes: list[ExperimentMode] | tuple[ExperimentMode, ...] = EXPERIMENT_MODES,
    top_k: int = 5,
) -> dict:
    """Score retrieval quality per mode without answer generation.

    Fast enough for full-dataset sweeps: one engine search per question, then
    each mode re-ranks the same result list by its own score column.
    """
    engine = RetrievalEngine(documents=documents, top_k=max(top_k, len(documents)))
    base_searches = [
        engine.search(question.question, top_k=max(top_k, len(documents))) for question in questions
    ]
    experiments = []
    for mode in modes:
        # Upstash measures its own live candidates; artifact modes re-rank
        # one shared engine result list by their own score column.
        searches = (
            [_upstash_search(question.question, top_k) for question in questions]
            if mode == "upstash"
            else base_searches
        )
        recalls_5: list[float] = []
        recalls_10: list[float] = []
        ranks: list[float] = []
        ndcgs: list[float] = []
        refusal_ok = 0
        evaluated = 0
        score_pairs: list[tuple[float, bool]] = []
        for question, retrieval in zip(questions, searches, strict=True):
            ranked = _rank(retrieval.results, mode)
            selected = ranked[: max(top_k, 10)]
            score_name = _MODE_SCORE[mode]
            best_score = getattr(selected[0], score_name) if selected else 0.0
            score_pairs.append((float(best_score), question.should_refuse))
            actual_refuse = not selected or best_score < _REFUSAL_THRESHOLDS[mode]
            refusal_ok += actual_refuse == question.should_refuse
            if question.should_refuse:
                continue
            evaluated += 1
            retrieved_ids = _unique_document_ids(selected)
            recalls_5.append(recall_at_k(question.expected_document_ids, retrieved_ids, 5))
            recalls_10.append(recall_at_k(question.expected_document_ids, retrieved_ids, 10))
            ranks.append(reciprocal_rank(question.expected_document_ids, retrieved_ids))
            ndcgs.append(ndcg_at_k(question.expected_document_ids, retrieved_ids, 10))
        experiments.append(
            {
                "mode": mode,
                "evaluated": evaluated,
                "question_count": len(questions),
                "recall_at_5": _mean(recalls_5),
                "recall_at_10": _mean(recalls_10),
                "mean_reciprocal_rank": _mean(ranks),
                "ndcg_at_10": _mean(ndcgs),
                "refusal_accuracy": (refusal_ok / len(questions)) if questions else 0.0,
                "recommended_refusal_threshold": _calibrate_threshold_from_scores(score_pairs),
            }
        )
    return {
        "question_count": len(questions),
        "top_k": top_k,
        "experiments": experiments,
    }


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _calibrate_threshold_from_scores(pairs: list[tuple[float, bool]]) -> float:
    """Pick the refusal threshold with best accuracy on (best_score, should_refuse)
    pairs, preferring the higher threshold on ties — same rule as
    _calibrate_refusal_threshold but without QuestionEvaluation wrappers."""
    best_threshold = 0.08
    best_accuracy = -1.0
    for threshold in sorted({0.0, *[score for score, _ in pairs], 1.0}):
        correct = sum((score < threshold) == expected for score, expected in pairs)
        accuracy = correct / max(1, len(pairs))
        if accuracy > best_accuracy or (accuracy == best_accuracy and threshold > best_threshold):
            best_accuracy = accuracy
            best_threshold = threshold
    return round(best_threshold, 6)


def tuning_subset(
    questions: list[EvaluationQuestion],
    per_category: int = 6,
    split: str = "development",
) -> list[EvaluationQuestion]:
    """Deterministic stratified sample for tuning sweeps.

    Takes the first `per_category` questions of each category from one split
    so sweeps run in minutes instead of hours; winners are confirmed on the
    full development split and finally on held-out test.
    """
    by_category: dict[str, list[EvaluationQuestion]] = {}
    for question in questions:
        if question.split != split:
            continue
        by_category.setdefault(question.category, []).append(question)
    subset: list[EvaluationQuestion] = []
    for category in sorted(by_category):
        subset.extend(by_category[category][: max(1, per_category)])
    return subset


DEFAULT_LAMBDA_SWEEP: tuple[float, ...] = (0.5, 0.7, 0.9)


def sweep_diversity_lambda(
    questions: list[EvaluationQuestion],
    documents: list[RetrievalDocument],
    lambda_options: list[float] | tuple[float, ...] | None = None,
    top_k: int = 10,
) -> list[dict]:
    """Compare MMR diversity strengths on retrieval quality (no generation).

    Rows sorted by recall then reciprocal rank, mirroring sweep_rerank_weights.
    """
    options = list(lambda_options) if lambda_options is not None else list(DEFAULT_LAMBDA_SWEEP)
    rows: list[dict] = []
    for lambda_param in options:
        engine = RetrievalEngine(
            documents=documents,
            top_k=max(top_k, len(documents)),
            diversity_lambda=lambda_param,
        )
        recalls: list[float] = []
        ranks: list[float] = []
        for question in questions:
            if question.should_refuse:
                continue
            retrieval = engine.search(question.question, top_k=max(top_k, len(documents)))
            retrieved_ids = _unique_document_ids(retrieval.results[: max(top_k, 10)])
            recalls.append(recall_at_k(question.expected_document_ids, retrieved_ids, top_k))
            ranks.append(reciprocal_rank(question.expected_document_ids, retrieved_ids))
        rows.append(
            {
                "diversity_lambda": lambda_param,
                "evaluated": len(recalls),
                "mean_recall_at_k": _mean(recalls),
                "mean_reciprocal_rank": _mean(ranks),
            }
        )
    rows.sort(key=lambda row: (row["mean_recall_at_k"], row["mean_reciprocal_rank"]), reverse=True)
    return rows


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
        answer_correctness=_average(item.answer_correctness for item in answerable),
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
                not item.actual_refuse and expected
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
    on_progress: ProgressCallback | None = None,
) -> dict:
    development = [question for question in questions if question.split == "development"]
    held_out = [question for question in questions if question.split == "test"]
    if not development or not held_out:
        raise ValueError("Provider evaluation requires development and held-out test splits.")

    total = len(development) + len(held_out)

    def report_development(completed: int, _total: int) -> None:
        if on_progress is not None:
            on_progress(completed, total)

    def report_held_out(completed: int, _total: int) -> None:
        if on_progress is not None:
            on_progress(len(development) + completed, total)

    development_results = _evaluate_provider_questions(
        development,
        retriever,
        generator,
        top_k,
        threshold=_REFUSAL_THRESHOLDS["rerank"],
        ragas_scorer=ragas_scorer,
        on_progress=report_development,
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
        on_progress=report_held_out,
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
    on_progress: ProgressCallback | None = None,
) -> list[QuestionEvaluation]:
    results: list[QuestionEvaluation] = []
    for index, question in enumerate(questions):
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
        retrieved_document_ids = _unique_document_ids(selected)
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
                answer_correctness=(
                    answer_correctness(answer, question.expected_answer)
                    if answerable
                    else None
                ),
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
        if on_progress is not None:
            on_progress(index + 1, len(questions))
    return results
