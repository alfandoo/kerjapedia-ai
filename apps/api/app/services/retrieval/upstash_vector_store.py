from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.retrieval.postprocessing import (
    apply_query_focus_adjustments,
    apply_relationship_adjustments,
    build_warnings,
    drop_heading_only_chunks,
    expand_context,
    mmr_select,
)
from app.services.retrieval.query import is_employment_query, understand_query
from app.services.retrieval.relationships import (
    RelationshipIndex,
    build_relationship_index,
)
from app.services.retrieval.reranker import (
    DEFAULT_RERANK_WEIGHTS,
    RerankWeights,
    rerank_score,
)
from app.services.retrieval.schemas import (
    RankedChunk,
    RetrievalDocument,
    RetrievalResponse,
)
from app.services.retrieval.scoring import (
    lexical_score,
    normalize_scores,
    reciprocal_rank_fusion,
)


@dataclass(frozen=True)
class UpstashVectorConfig:
    url: str
    token: str
    dimension: int = 1536
    namespace: str = "production"


class UpstashVectorStore:
    """Retrieval store backed by Upstash Vector with hybrid dense+sparse search.

    Dense embeddings: text-embedding-3-small (1536d) via OpenAI
    Sparse: BM25 lexical scoring
    """

    def __init__(
        self,
        config: UpstashVectorConfig,
        openai_api_key: str,
        reranker_provider: str = "heuristic",
        reranker_model: str = "bge-reranker-v2-m3",
        fail_closed: bool = False,
        allow_unpublished: bool = True,
        relationship_index: RelationshipIndex | None = None,
        rerank_weights: RerankWeights | None = None,
        diversity_lambda: float = 0.7,
        hybrid_alpha: float = 0.7,
        semantic_limit: int = 100,
        cross_encoder_top_n: int = 50,
        cross_encoder_blend_weight: float = 0.75,
        mmr_max_per_document: int = 3,
        mmr_max_per_article: int = 2,
        expansion_max: int = 4,
        expansion_score_decay: float = 0.85,
    ) -> None:
        from upstash_vector import Index

        self.config = config
        self.reranker_provider = reranker_provider
        self.reranker_model = reranker_model
        self.fail_closed = fail_closed
        self.allow_unpublished = allow_unpublished
        self.relationship_index = relationship_index or build_relationship_index([])
        self.rerank_weights = rerank_weights or DEFAULT_RERANK_WEIGHTS
        self.diversity_lambda = diversity_lambda
        self.hybrid_alpha = hybrid_alpha
        self.semantic_limit = semantic_limit
        self.cross_encoder_top_n = cross_encoder_top_n
        self.cross_encoder_blend_weight = cross_encoder_blend_weight
        self.mmr_max_per_document = mmr_max_per_document
        self.mmr_max_per_article = mmr_max_per_article
        self.expansion_max = expansion_max
        self.expansion_score_decay = expansion_score_decay

        self._index = Index(url=config.url, token=config.token)
        self._openai_client = None
        self._openai_api_key = openai_api_key

    def _get_openai_client(self):
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=self._openai_api_key, timeout=60.0)
        return self._openai_client

    def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        client = self._get_openai_client()
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
            dimensions=self.config.dimension,
        )
        ordered = sorted(response.data, key=lambda item: int(item.index))
        return [item.embedding for item in ordered]

    @staticmethod
    def _bm25_sparse(text: str, k1: float = 1.5, b: float = 0.75) -> dict[int, float]:
        tokens = text.lower().split()
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        scores = {}
        for token, count in tf.items():
            token_hash = hash(token) % (2**31)
            scores[token_hash] = count * (k1 + 1) / (count + k1 * (1 - b + b * len(tokens) / 100))
        return scores

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """Upsert chunks to Upstash Vector.

        Each chunk dict must have:
        - chunk_id: str
        - text: str (will be embedded)
        - metadata: dict
        """
        from upstash_vector import Data, SparseVector

        upserted = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            texts = [c["text"] for c in batch]
            dense_vectors = self._embed_dense(texts)

            data_list = []
            for i, chunk in enumerate(batch):
                sparse_dict = self._bm25_sparse(chunk["text"])
                sparse = SparseVector(
                    indices=list(sparse_dict.keys()),
                    values=list(sparse_dict.values()),
                )
                data_list.append(
                    Data(
                        id=chunk["chunk_id"],
                        vector=dense_vectors[i],
                        sparse_vector=sparse,
                        data=chunk["text"],
                        metadata=chunk.get("metadata", {}),
                    )
                )

            self._index.upsert(vectors=data_list)
            upserted += len(batch)

        return upserted

    def query(
        self,
        query_text: str,
        top_k: int = 20,
        namespace: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query Upstash Vector with hybrid dense+sparse search."""
        from upstash_vector import SparseVector

        dense_vector = self._embed_dense([query_text])[0]
        sparse_dict = self._bm25_sparse(query_text)
        sparse = SparseVector(
            indices=list(sparse_dict.keys()),
            values=list(sparse_dict.values()),
        )

        ns = namespace or self.config.namespace
        response = self._index.query(
            vector=dense_vector,
            sparse_vector=sparse,
            top_k=top_k,
            include_metadata=True,
            include_data=False,
        )

        results = []
        for match in (response or []):
            results.append({
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata or {},
            })
        return results

    def delete_namespace(self, namespace: str | None = None) -> None:
        ns = namespace or self.config.namespace
        self._index.delete(delete_all=True, namespace=ns)

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        retrieval_query: str | None = None,
        context_topics: tuple[str, ...] = (),
        context_document_ids: tuple[str, ...] = (),
        context_articles: tuple[str, ...] = (),
        rerank_weights: RerankWeights | None = None,
    ) -> RetrievalResponse:
        """Full retrieval pipeline: query understanding -> vector search -> rerank -> postprocess."""
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

        timing: dict[str, float] = {}
        t_start = time.perf_counter()

        rewrites = list(understanding.rewritten_queries[:3]) or [understanding.normalized_query]
        candidates: list[RetrievalDocument] = []
        seen_ids: set[str] = set()

        for rewrite in rewrites:
            matches = self.query(rewrite, top_k=self.semantic_limit)
            for match in matches:
                chunk_id = match["id"]
                if chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)
                meta = match["metadata"]
                candidates.append(RetrievalDocument(
                    chunk_id=chunk_id,
                    document_id=meta.get("document_id", ""),
                    text=meta.get("retrieval_text", meta.get("text", "")),
                    chapter=meta.get("chapter"),
                    section=meta.get("section"),
                    article=meta.get("article"),
                    paragraph=meta.get("paragraph"),
                    page_start=meta.get("page_start", 0),
                    page_end=meta.get("page_end", 0),
                    token_count=meta.get("token_count", 0),
                    topics=meta.get("topics", []),
                    legal_status=meta.get("legal_status", "active"),
                    source_url=meta.get("source_url", ""),
                    retrieval_text=meta.get("retrieval_text"),
                    build_id=meta.get("build_id"),
                    embedding_model=meta.get("embedding_model"),
                    metadata=meta,
                    document_version=meta.get("document_version"),
                    publication_status=meta.get("publication_status", "published"),
                    verification_status=meta.get("verification_status", "verified"),
                    is_current=meta.get("is_current", True),
                ))

        timing["vector_query"] = round((time.perf_counter() - t_start) * 1000, 1)

        lexical_scores = {
            doc.chunk_id: max(
                lexical_score(rq, doc) for rq in understanding.rewritten_queries
            )
            for doc in candidates
        }

        by_id = {doc.chunk_id: doc for doc in candidates}
        normalized_lexical = normalize_scores(lexical_scores)

        active_rerank_weights = rerank_weights or self.rerank_weights
        ranked: list[RankedChunk] = []
        for doc in candidates:
            ls = normalized_lexical.get(doc.chunk_id, 0.0)
            rs = rerank_score(
                understanding.normalized_query,
                doc,
                provider=self.reranker_provider,
                model=self.reranker_model,
            )
            final = (
                active_rerank_weights.lexical * ls
                + active_rerank_weights.semantic * rs
            )
            ranked.append(RankedChunk(
                document=doc,
                lexical_score=ls,
                semantic_score=0.0,
                fusion_score=ls,
                rerank_score=rs,
                final_score=final,
                match_reasons=[],
            ))

        ranked.sort(key=lambda r: r.final_score, reverse=True)
        ranked = drop_heading_only_chunks(ranked)
        warnings = build_warnings(ranked, understanding)
        ranked = apply_query_focus_adjustments(ranked, understanding)
        ranked = apply_relationship_adjustments(
            ranked, self.relationship_index, understanding
        )
        ranked = mmr_select(
            ranked,
            lambda_per_document=self.mmr_max_per_document,
            lambda_per_article=self.mmr_max_per_article,
            diversity_lambda=self.diversity_lambda,
        )
        ranked = expand_context(
            ranked,
            by_id,
            max_expansion=self.expansion_max,
            score_decay=self.expansion_score_decay,
        )
        ranked = ranked[:top_k]

        return RetrievalResponse(
            query=understanding,
            results=ranked,
            warnings=warnings,
            should_refuse=False,
            refusal_reason=None,
            timing=timing,
        )
