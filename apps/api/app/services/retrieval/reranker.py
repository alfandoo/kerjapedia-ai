from __future__ import annotations

from app.services.retrieval.schemas import QueryUnderstanding, RetrievalDocument
from app.services.retrieval.scoring import tokenize


def rerank_score(
    query: QueryUnderstanding,
    document: RetrievalDocument,
    lexical_score: float,
    semantic_score: float,
    fusion_score: float,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    query_terms = set(tokenize(" ".join(query.rewritten_queries)))
    text_terms = set(tokenize(document.text))
    overlap = len(query_terms.intersection(text_terms))
    overlap_score = overlap / max(1, len(query_terms))

    topic_boost = 0.0
    if query.detected_topics and set(query.detected_topics).intersection(document.topics):
        topic_boost = 0.2
        reasons.append("topic_match")

    article_boost = 0.0
    if query.filters.get("article") and query.filters.get("article") == document.article:
        article_boost = 0.25
        reasons.append("article_match")

    status_penalty = 0.0
    if document.legal_status in {"revoked", "historical"}:
        status_penalty = 0.2
        reasons.append("historical_or_revoked_penalty")
    elif document.legal_status == "needs_verification":
        status_penalty = 0.05
        reasons.append("needs_verification_warning")

    score = (
        fusion_score * 0.45
        + lexical_score * 0.2
        + max(semantic_score, 0) * 0.2
        + overlap_score * 0.15
        + topic_boost
        + article_boost
        - status_penalty
    )
    return score, reasons
