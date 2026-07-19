from __future__ import annotations

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


def reciprocal_rank(expected_ids: Iterable[str], retrieved_ids: list[str]) -> float:
    expected = set(expected_ids)
    for index, document_id in enumerate(retrieved_ids, start=1):
        if document_id in expected:
            return round(1 / index, 6)
    return 0.0


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
    if not answer.citations:
        return 0.0
    support_tokens = set()
    for citation in answer.citations:
        support_tokens.update(_content_tokens(citation.quote))
    answer_tokens = _content_tokens(answer.answer)
    if not answer_tokens:
        return 0.0
    return round(len(answer_tokens.intersection(support_tokens)) / len(answer_tokens), 6)


def _content_tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(value.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }
