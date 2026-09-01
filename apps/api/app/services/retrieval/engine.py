from __future__ import annotations

from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.filtering import matches_filters
from app.services.retrieval.postprocessing import (
    apply_query_focus_adjustments,
    apply_relationship_adjustments,
    build_warnings,
    diversify_ranked,
    drop_heading_only_chunks,
    expand_context,
)
from app.services.retrieval.query import is_employment_query, understand_query
from app.services.retrieval.relationships import (
    RelationshipIndex,
    build_relationship_index,
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

    def search(
        self,
        query: str,
        top_k: int | None = None,
        *,
        retrieval_query: str | None = None,
        context_topics: tuple[str, ...] = (),
        context_document_ids: tuple[str, ...] = (),
        context_articles: tuple[str, ...] = (),
    ) -> RetrievalResponse:
        limit = top_k or self.top_k
        understanding = understand_query(
            query,
            retrieval_query=retrieval_query,
            context_topics=context_topics,
            context_document_ids=context_document_ids,
            context_articles=context_articles,
        )
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
        ranked = apply_relationship_adjustments(ranked, self.relationship_index)
        ranked = apply_query_focus_adjustments(
            ranked,
            understanding.normalized_retrieval_query,
        )
        ranked = drop_heading_only_chunks(ranked)
        ranked = diversify_ranked(ranked)
        expanded = expand_context(ranked[:limit], candidates)
        warnings = build_warnings(expanded, self.relationship_index)
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
