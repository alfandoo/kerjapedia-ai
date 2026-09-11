from __future__ import annotations

import re
from collections import defaultdict

from app.services.retrieval.relationships import (
    RelationshipIndex,
    document_superseding_ids,
)
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument
from app.services.retrieval.scoring import tokenize

_LEGAL_HEADING_PATTERN = re.compile(
    r"^(?:bab\s+[ivxlcdm]+|bagian\s+(?:ke\S+|[ivxlcdm]+)|pasal\s+\d+[a-z]?)\b",
    re.IGNORECASE,
)
_SUBSTANTIVE_TERMS = {
    "berhak",
    "berlaku",
    "dapat",
    "diberikan",
    "dibayarkan",
    "dikenai",
    "dilarang",
    "ditetapkan",
    "harus",
    "melakukan",
    "membayar",
    "menerima",
    "mengatur",
    "memperoleh",
    "wajib",
    "applies",
    "entitled",
    "must",
    "prohibited",
    "required",
    "shall",
}
_FOCUS_STOPWORDS = {
    "apa",
    "apakah",
    "bagaimana",
    "karena",
    "perusahaan",
    "pekerja",
    "buruh",
    "hubungan",
    "kerja",
    "pemutusan",
    "phk",
    "syarat",
    "yang",
}


def is_heading_only(document: RetrievalDocument) -> bool:
    """Return true for short legal structure labels without an operative rule."""

    normalized = " ".join(document.text.split()).strip(" .:;-—")
    if not normalized or not _LEGAL_HEADING_PATTERN.match(normalized):
        return False
    words = re.findall(r"[\w-]+", normalized.casefold())
    return len(words) <= 12 and not _SUBSTANTIVE_TERMS.intersection(words)


def drop_heading_only_chunks(ranked: list[RankedChunk]) -> list[RankedChunk]:
    """Prefer substantive chunks while retaining headings as an empty-result fallback."""

    substantive = [item for item in ranked if not is_heading_only(item.document)]
    return substantive or ranked


def apply_query_focus_adjustments(
    ranked: list[RankedChunk],
    normalized_query: str,
) -> list[RankedChunk]:
    """Boost explicit distinguishing terms without turning inferred topics into filters."""

    if len(ranked) < 2:
        return ranked
    query_terms = {
        term
        for term in tokenize(normalized_query)
        if len(term) >= 5 and term not in _FOCUS_STOPWORDS
    }
    if not query_terms:
        return ranked
    text_terms = [set(tokenize(item.document.text)) for item in ranked]
    max_frequency = max(1, int(len(ranked) * 0.7))
    focus_terms = {
        term
        for term in query_terms
        if 1 <= sum(term in terms for terms in text_terms) <= max_frequency
    }
    if not focus_terms:
        return ranked

    adjusted: list[RankedChunk] = []
    for item, terms in zip(ranked, text_terms, strict=True):
        matches = sorted(focus_terms.intersection(terms))
        if not matches:
            adjusted.append(item)
            continue
        boost = min(0.18, 0.09 * len(matches))
        adjusted.append(
            RankedChunk(
                document=item.document,
                lexical_score=item.lexical_score,
                semantic_score=item.semantic_score,
                fusion_score=item.fusion_score,
                rerank_score=item.rerank_score,
                final_score=round(item.final_score + boost, 6),
                match_reasons=[*item.match_reasons, "explicit_query_term:" + ",".join(matches)],
            )
        )
    return sorted(adjusted, key=lambda item: item.final_score, reverse=True)


def apply_relationship_adjustments(
    ranked: list[RankedChunk],
    relationship_index: RelationshipIndex,
) -> list[RankedChunk]:
    if not relationship_index.superseded_by:
        return ranked
    ranked_ids = {item.document.document_id for item in ranked}
    adjusted: list[RankedChunk] = []
    for item in ranked:
        penalty = 0.0
        boost = 0.0
        reasons = list(item.match_reasons)
        superseding_ids = document_superseding_ids(relationship_index, item.document.document_id)
        if superseding_ids:
            penalty = 0.3 if item.document.legal_status in {"revoked", "historical"} else 0.15
            reasons.append("superseded_by_newer_document")
        if any(item_id in ranked_ids for item_id in superseding_ids):
            reasons.append("superseding_document_also_retrieved")
            if item.document.legal_status in {"revoked", "historical"}:
                penalty = max(penalty, 0.4)
        if any(
            item_id in ranked_ids
            for item_id in relationship_index.superseding.get(item.document.document_id, [])
        ):
            boost = 0.05
            reasons.append("document_version_supersedes_retrieved_older")
        adjusted.append(
            RankedChunk(
                document=item.document,
                lexical_score=item.lexical_score,
                semantic_score=item.semantic_score,
                fusion_score=item.fusion_score,
                rerank_score=item.rerank_score,
                final_score=round(item.final_score - penalty + boost, 6),
                match_reasons=reasons,
            )
        )
    return sorted(adjusted, key=lambda item: item.final_score, reverse=True)


def diversify_ranked(
    ranked: list[RankedChunk],
    *,
    max_per_document: int = 3,
    max_per_article: int = 1,
) -> list[RankedChunk]:
    counts: dict[str, int] = defaultdict(int)
    article_counts: dict[tuple[str, str], int] = defaultdict(int)
    result: list[RankedChunk] = []
    for item in ranked:
        document_id = item.document.document_id
        if counts[document_id] >= max_per_document:
            continue
        article_key = (
            document_id,
            item.document.article or f"__unstructured__:{item.document.chunk_id}",
        )
        if article_counts[article_key] >= max_per_article:
            continue
        counts[document_id] += 1
        article_counts[article_key] += 1
        result.append(item)
    return result


def expand_context(
    ranked: list[RankedChunk],
    candidates: list[RetrievalDocument],
) -> list[RankedChunk]:
    if not ranked:
        return []
    by_document: dict[str, list[RetrievalDocument]] = defaultdict(list)
    for document in candidates:
        by_document[document.document_id].append(document)
    for documents in by_document.values():
        documents.sort(
            key=lambda item: (
                item.page_start,
                item.char_start,
                item.chunk_id,
            )
        )
    selected_ids = {item.document.chunk_id for item in ranked}
    expanded = list(ranked)
    for item in ranked[:3]:
        siblings = by_document[item.document.document_id]
        index = next(
            (
                idx
                for idx, document in enumerate(siblings)
                if document.chunk_id == item.document.chunk_id
            ),
            None,
        )
        if index is None:
            continue
        for sibling in siblings[max(0, index - 1) : index + 2]:
            if sibling.chunk_id in selected_ids:
                continue
            if is_heading_only(sibling):
                continue
            same_article = (
                item.document.article is not None and item.document.article == sibling.article
            )
            adjacent_page = abs(item.document.page_start - sibling.page_start) <= 1
            if not same_article and not adjacent_page:
                continue
            selected_ids.add(sibling.chunk_id)
            expanded.append(
                RankedChunk(
                    document=sibling,
                    lexical_score=0.0,
                    semantic_score=0.0,
                    fusion_score=0.0,
                    rerank_score=round(item.rerank_score * 0.85, 6),
                    final_score=round(item.final_score * 0.85, 6),
                    match_reasons=["context_expansion"],
                )
            )
    return sorted(expanded, key=lambda result: result.final_score, reverse=True)


def build_warnings(
    ranked: list[RankedChunk],
    relationship_index: RelationshipIndex,
) -> list[str]:
    warnings: list[str] = []
    statuses = {item.document.legal_status for item in ranked}
    if "needs_verification" in statuses or any(
        item.document.verification_status != "verified" for item in ranked
    ):
        warnings.append("retrieved_source_status_needs_verification")
    if {"revoked", "historical"}.intersection(statuses):
        warnings.append("retrieved_source_contains_historical_or_revoked_document")
    superseded_docs = [
        item
        for item in ranked
        if document_superseding_ids(relationship_index, item.document.document_id)
    ]
    if superseded_docs:
        warnings.append("retrieved_source_superseded_by_newer_document")
        if any(item.document.legal_status in {"revoked", "historical"} for item in superseded_docs):
            warnings.append("retrieved_source_revoked_or_superseded_document")
    return warnings
