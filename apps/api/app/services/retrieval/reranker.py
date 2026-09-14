from __future__ import annotations

from dataclasses import dataclass

from app.services.retrieval.schemas import QueryUnderstanding, RetrievalDocument
from app.services.retrieval.scoring import tokenize


@dataclass(frozen=True)
class RerankWeights:
    """Tunable rerank coefficients. Defaults preserve the long-standing
    production behavior; overrides come from calibration runs whose
    winning config is recorded in evaluation reports."""

    fusion: float = 0.45
    lexical: float = 0.2
    semantic: float = 0.2
    overlap: float = 0.15
    topic_boost: float = 0.2
    article_boost: float = 0.25
    context_boost_doc: float = 0.08
    context_boost_article: float = 0.02
    status_penalty_revoked: float = 0.2
    status_penalty_unverified: float = 0.05


DEFAULT_RERANK_WEIGHTS = RerankWeights()


def rerank_score(
    query: QueryUnderstanding,
    document: RetrievalDocument,
    lexical_score: float,
    semantic_score: float,
    fusion_score: float,
    *,
    weights: RerankWeights = DEFAULT_RERANK_WEIGHTS,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    query_terms = set(tokenize(" ".join(query.rewritten_queries)))
    text_terms = set(tokenize(document.retrieval_text or document.text))
    overlap = len(query_terms.intersection(text_terms))
    overlap_score = overlap / max(1, len(query_terms))

    topic_boost = 0.0
    if query.detected_topics and set(query.detected_topics).intersection(document.topics):
        topic_boost = weights.topic_boost
        reasons.append("topic_match")

    article_boost = 0.0
    if query.filters.get("article") and query.filters.get("article") == document.article:
        article_boost = weights.article_boost
        reasons.append("article_match")

    context_boost = 0.0
    if document.document_id in query.context_document_ids:
        context_boost += weights.context_boost_doc
        reasons.append("conversation_document_match")
    if document.article and document.article in query.context_articles:
        context_boost += weights.context_boost_article
        reasons.append("conversation_article_hint")

    status_penalty = 0.0
    if document.legal_status in {"revoked", "historical"}:
        status_penalty = weights.status_penalty_revoked
        reasons.append("historical_or_revoked_penalty")
    elif document.legal_status == "needs_verification":
        status_penalty = weights.status_penalty_unverified
        reasons.append("needs_verification_warning")

    score = (
        fusion_score * weights.fusion
        + lexical_score * weights.lexical
        + max(semantic_score, 0) * weights.semantic
        + overlap_score * weights.overlap
        + topic_boost
        + article_boost
        + context_boost
        - status_penalty
    )
    return score, reasons
