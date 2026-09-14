from __future__ import annotations

import math
import re
from collections import Counter

from app.services.retrieval.schemas import RetrievalDocument

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def lexical_score(query: str, document: RetrievalDocument) -> float:
    query_terms = tokenize(query)
    if not query_terms:
        return 0.0

    term_counts = Counter(tokenize(document.retrieval_text or document.text))
    length_norm = math.sqrt(max(1, len(term_counts)))
    score = 0.0
    for term in query_terms:
        if term in term_counts:
            score += 1.0 + math.log1p(term_counts[term])
    return score / length_norm


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    """Min-max normalize a per-query score map to [0, 1].

    Raw Pinecone scores live on different scales per rewritten query, so
    carrying them raw into the reranker gives the semantic term a
    query-dependent weight. Uniform input maps to 1.0.
    """
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    if hi <= lo:
        return {key: 1.0 for key in scores}
    return {key: (value - lo) / (hi - lo) for key, value in scores.items()}
