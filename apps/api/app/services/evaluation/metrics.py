from __future__ import annotations

import math
import re
from collections.abc import Iterable

from app.services.answering.schemas import AnswerResponse

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "adalah",
    "atau",
    "dan",
    "dari",
    "dengan",
    "di",
    "ini",
    "itu",
    "ke",
    "pada",
    "yang",
    "untuk",
    "berdasarkan",
    "dokumen",
    "tersedia",
}


def recall_at_k(expected_ids: Iterable[str], retrieved_ids: list[str], k: int = 5) -> float:
    expected = set(expected_ids)
    if not expected:
        return 0.0
    return round(len(expected.intersection(retrieved_ids[:k])) / len(expected), 6)


def precision_at_k(expected_ids: Iterable[str], retrieved_ids: list[str], k: int = 5) -> float:
    """Precision@K: proportion of retrieved documents that are relevant."""
    expected = set(expected_ids)
    if not expected:
        return 0.0
    retrieved_top_k = retrieved_ids[:k]
    if not retrieved_top_k:
        return 0.0
    return round(len(expected.intersection(retrieved_top_k)) / len(retrieved_top_k), 6)


def hit_rate(expected_ids: Iterable[str], retrieved_ids: list[str], k: int = 5) -> float:
    """Hit Rate: 1 if at least one relevant document is in top-K, else 0."""
    expected = set(expected_ids)
    if not expected:
        return 0.0
    retrieved_top_k = retrieved_ids[:k]
    return 1.0 if expected.intersection(retrieved_top_k) else 0.0


def reciprocal_rank(expected_ids: Iterable[str], retrieved_ids: list[str]) -> float:
    expected = set(expected_ids)
    for index, document_id in enumerate(retrieved_ids, start=1):
        if document_id in expected:
            return round(1 / index, 6)
    return 0.0


def ndcg_at_k(expected_ids: Iterable[str], retrieved_ids: list[str], k: int = 10) -> float:
    expected = set(expected_ids)
    if not expected:
        return 0.0
    # A document occupies one rank position no matter how many of its chunks
    # were retrieved; without this, repeated chunks push DCG above ideal.
    ranked = list(dict.fromkeys(retrieved_ids))[:k]
    dcg = sum(
        1.0 / math.log2(index + 2)
        for index, document_id in enumerate(ranked)
        if document_id in expected
    )
    ideal_hits = min(len(expected), k)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return round(dcg / ideal, 6) if ideal else 0.0


def citation_correctness(
    answer: AnswerResponse,
    expected_document_ids: Iterable[str],
    expected_articles: Iterable[str],
) -> float:
    expected_documents = set(expected_document_ids)
    if not answer.citations:
        return 0.0
    exact_articles = {
        article for article in expected_articles if article.lower().startswith("pasal ")
    }
    correct = 0.0
    for citation in answer.citations:
        if citation.document_id not in expected_documents:
            continue
        if exact_articles and citation.article and citation.article not in exact_articles:
            correct += 0.5
        else:
            correct += 1.0
    return round(correct / len(answer.citations), 6)


def faithfulness(answer: AnswerResponse) -> float:
    if answer.claims:
        return round(
            sum(claim.support_score if claim.supported else 0.0 for claim in answer.claims)
            / len(answer.claims),
            6,
        )
    if not answer.citations:
        return 0.0
    support_tokens = set()
    for citation in answer.citations:
        support_tokens.update(_content_tokens(citation.quote))
    answer_tokens = _content_tokens(answer.answer)
    if not answer_tokens:
        return 0.0
    return round(len(answer_tokens.intersection(support_tokens)) / len(answer_tokens), 6)


def unsupported_claim_rate(answer: AnswerResponse) -> float:
    if not answer.claims:
        return 1.0 if answer.answer and not answer.refusal_reason else 0.0
    unsupported = sum(not claim.supported for claim in answer.claims)
    return round(unsupported / len(answer.claims), 6)


def answer_correctness(answer: AnswerResponse, expected_answer: str) -> float:
    """Token overlap between generated answer and expected answer.

    Uses Jaccard similarity of content tokens (stopwords removed) as a
    lightweight correctness signal.  Returns 0.0 when either side is empty.
    """
    answer_tokens = _content_tokens(answer.answer)
    expected_tokens = _content_tokens(expected_answer)
    if not answer_tokens or not expected_tokens:
        return 0.0
    intersection = answer_tokens & expected_tokens
    union = answer_tokens | expected_tokens
    return round(len(intersection) / len(union), 6)


def _content_tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(value.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }
