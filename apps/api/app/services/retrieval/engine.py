from __future__ import annotations

from collections import defaultdict

from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.filtering import matches_filters
from app.services.retrieval.query import is_employment_query, understand_query
from app.services.retrieval.relationships import (
    RelationshipIndex,
    build_relationship_index,
    document_superseding_ids,
)
from app.services.retrieval.reranker import rerank_score
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument, RetrievalResponse
from app.services.retrieval.scoring import cosine_similarity, lexical_score, reciprocal_rank_fusion


class RetrievalEngine:
    def __init__(
        self,
        documents: list[RetrievalDocument],
        min_final_score: float = 0.08,
        top_k: int = 5,
        relationship_index: RelationshipIndex | None = None,
    ) -> None:
        self.documents = documents
        self.min_final_score = min_final_score
        self.top_k = top_k
        self.relationship_index = relationship_index or build_relationship_index([])
        self.embedding_provider = HashEmbeddingProvider()

    def search(self, query: str, top_k: int | None = None) -> RetrievalResponse:
        limit = top_k or self.top_k
        understanding = understand_query(query)
        if not is_employment_query(understanding):
            return RetrievalResponse(
                query=understanding,
                results=[],
                warnings=["query_outside_employment_scope"],
                should_refuse=True,
                refusal_reason="out_of_scope_query",
            )
        candidates = [
            document
            for document in self.documents
            if matches_filters(document, understanding.filters)
        ]

        if not candidates and understanding.filters:
            candidates = self.documents

        query_vector = self.embedding_provider.embed([" ".join(understanding.rewritten_queries)])[0]

        lexical_scores = {
            document.chunk_id: max(
                lexical_score(rewritten_query, document)
                for rewritten_query in understanding.rewritten_queries
            )
            for document in candidates
        }
        semantic_scores = {
            document.chunk_id: cosine_similarity(query_vector, document.embedding)
            for document in candidates
        }

        lexical_ranking = [
            chunk_id
            for chunk_id, score in sorted(
                lexical_scores.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if score > 0
        ]
        semantic_ranking = [
            chunk_id
            for chunk_id, score in sorted(
                semantic_scores.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if score > 0
        ]
        fusion_scores = reciprocal_rank_fusion([lexical_ranking, semantic_ranking])
        by_id = {document.chunk_id: document for document in candidates}

        ranked: list[RankedChunk] = []
        for chunk_id, fusion_score in fusion_scores.items():
            document = by_id[chunk_id]
            rerank, reasons = rerank_score(
                understanding,
                document,
                lexical_scores.get(chunk_id, 0.0),
                semantic_scores.get(chunk_id, 0.0),
                fusion_score,
            )
            ranked.append(
                RankedChunk(
                    document=document,
                    lexical_score=round(lexical_scores.get(chunk_id, 0.0), 6),
                    semantic_score=round(semantic_scores.get(chunk_id, 0.0), 6),
                    fusion_score=round(fusion_score, 6),
                    rerank_score=round(rerank, 6),
                    final_score=round(rerank, 6),
                    match_reasons=reasons,
                )
            )

        ranked.sort(key=lambda item: item.final_score, reverse=True)
        ranked = self._apply_relationship_adjustments(ranked)
        expanded = self._expand_context(ranked[:limit], candidates)
        warnings = self._build_warnings(expanded)
        should_refuse = not expanded or expanded[0].final_score < self.min_final_score
        refusal_reason = None
        if should_refuse:
            refusal_reason = "no_retrieved_chunk_passed_minimum_score"

        return RetrievalResponse(
            query=understanding,
            results=expanded[:limit],
            warnings=warnings,
            should_refuse=should_refuse,
            refusal_reason=refusal_reason,
        )

    def _apply_relationship_adjustments(
        self,
        ranked: list[RankedChunk],
    ) -> list[RankedChunk]:
        if not self.relationship_index.superseded_by:
            return ranked
        ranked_ids = {item.document.document_id for item in ranked}
        adjusted: list[RankedChunk] = []
        for item in ranked:
            penalty = 0.0
            boost = 0.0
            reasons = list(item.match_reasons)
            superseding_ids = document_superseding_ids(
                self.relationship_index,
                item.document.document_id,
            )
            if superseding_ids:
                penalty = (
                    0.3 if item.document.legal_status in {"revoked", "historical"} else 0.15
                )
                reasons.append("superseded_by_newer_document")
            for superseding_id in superseding_ids:
                if superseding_id in ranked_ids:
                    reasons.append("superseding_document_also_retrieved")
                    if item.document.legal_status in {"revoked", "historical"}:
                        penalty = max(penalty, 0.4)
            for older_id in self.relationship_index.superseding.get(
                item.document.document_id,
                [],
            ):
                if older_id in ranked_ids:
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
        adjusted.sort(key=lambda item: item.final_score, reverse=True)
        return adjusted

    def _expand_context(
        self,
        ranked: list[RankedChunk],
        candidates: list[RetrievalDocument],
    ) -> list[RankedChunk]:
        if not ranked:
            return []

        by_document = defaultdict(list)
        for document in candidates:
            by_document[document.document_id].append(document)
        for documents in by_document.values():
            documents.sort(key=lambda item: (item.page_start, item.chunk_id))

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

        expanded.sort(key=lambda result: result.final_score, reverse=True)
        return expanded

    def _build_warnings(self, ranked: list[RankedChunk]) -> list[str]:
        warnings: list[str] = []
        statuses = {item.document.legal_status for item in ranked}
        if "needs_verification" in statuses:
            warnings.append("retrieved_source_status_needs_verification")
        if {"revoked", "historical"}.intersection(statuses):
            warnings.append("retrieved_source_contains_historical_or_revoked_document")
        superseded_docs = [
            item
            for item in ranked
            if document_superseding_ids(
                self.relationship_index,
                item.document.document_id,
            )
        ]
        if superseded_docs:
            warnings.append("retrieved_source_superseded_by_newer_document")
            if any(
                item.document.legal_status in {"revoked", "historical"}
                for item in superseded_docs
            ):
                warnings.append("retrieved_source_revoked_or_superseded_document")
        return warnings
