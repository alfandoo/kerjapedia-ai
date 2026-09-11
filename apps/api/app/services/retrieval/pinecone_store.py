from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from app.services.ingestion.embeddings import EmbeddingProvider, embed_hybrid
from app.services.ingestion.schemas import DocumentMetadata, EmbeddedChunk
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
from app.services.retrieval.schemas import (
    RankedChunk,
    RetrievalDocument,
    RetrievalResponse,
)
from app.services.retrieval.scoring import lexical_score, reciprocal_rank_fusion

PINECONE_METADATA_TEXT_LIMIT = 12_000


@dataclass(frozen=True)
class PineconeConfig:
    api_key: str
    index_name: str = "kerjapedia-regulations-v2"
    namespace: str = "production"
    cloud: str = "aws"
    region: str = "us-east-1"
    dimension: int = 1024
    metric: str = "dotproduct"


class PineconeRetrievalStore:
    def __init__(
        self,
        config: PineconeConfig,
        embedding_provider: EmbeddingProvider,
        reranker_provider: str = "heuristic",
        reranker_model: str = "bge-reranker-v2-m3",
        fail_closed: bool = False,
        allow_unpublished: bool = True,
        relationship_index: RelationshipIndex | None = None,
    ) -> None:
        self.config = config
        self.embedding_provider = embedding_provider
        self.reranker_provider = reranker_provider
        self.reranker_model = reranker_model
        self.fail_closed = fail_closed
        self.allow_unpublished = allow_unpublished
        self.relationship_index = relationship_index or build_relationship_index([])
        self._client = None
        self._index = None
        self._filter_support_cache: dict[str, frozenset[str]] = {}

    def _supported_filter_fields(self) -> frozenset[str]:
        """Metadata keys present in this namespace (probed once, cached).

        A filter clause on an absent field matches nothing, so unsupported
        dimensions are dropped with a warning instead of emptying results.
        Probe failures fail open: assume legacy and warn.
        """
        namespace = self.config.namespace
        cached = self._filter_support_cache.get(namespace)
        if cached is not None:
            return cached
        try:
            response = self._pinecone_index().query(
                vector=[0.0] * self.config.dimension,
                top_k=1,
                namespace=namespace,
                include_metadata=True,
                include_values=False,
            )
            matches = list(getattr(response, "matches", []) or [])
            if not matches:
                supported: frozenset[str] = frozenset()
            else:
                supported = frozenset(_match_metadata(matches[0]).keys())
        except Exception:
            supported = frozenset()
        self._filter_support_cache[namespace] = supported
        return supported

    def _drop_unsupported_filter_fields(
        self, pinecone_filter: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Drop new-dimension clauses the namespace cannot satisfy."""
        if not pinecone_filter:
            return pinecone_filter, []
        referenced = {field for field in _NEW_FILTER_FIELDS if field in pinecone_filter}
        if not referenced:
            return pinecone_filter, []
        supported = self._supported_filter_fields()
        dropped = sorted(field for field in referenced if field not in supported)
        if not dropped:
            return pinecone_filter, []
        kept = {key: value for key, value in pinecone_filter.items() if key not in dropped}
        warnings = [f"filter_unsupported_by_index:{field}" for field in dropped]
        return (kept or None), warnings

    def ensure_index(self) -> None:
        client = self._pinecone_client()
        names = client.indexes.list().names()
        if self.config.index_name not in names:
            try:
                from pinecone import ServerlessSpec
            except ImportError as exc:
                raise RuntimeError("pinecone is required for VECTOR_STORE=pinecone.") from exc
            client.indexes.create(
                name=self.config.index_name,
                dimension=self.config.dimension,
                metric=self.config.metric,
                spec=ServerlessSpec(cloud=self.config.cloud, region=self.config.region),
            )
            return
        description = client.indexes.describe(self.config.index_name)
        dimension = int(
            getattr(description, "dimension", 0)
            or (description.get("dimension", 0) if isinstance(description, dict) else 0)
        )
        metric = str(
            getattr(description, "metric", "")
            or (description.get("metric", "") if isinstance(description, dict) else "")
        )
        if dimension and dimension != self.config.dimension:
            raise RuntimeError(
                f"Pinecone index dimension is {dimension}; expected {self.config.dimension}."
            )
        if metric and metric != self.config.metric:
            raise RuntimeError(f"Pinecone index metric is {metric}; expected {self.config.metric}.")

    def is_ready(self) -> bool:
        if not self.config.api_key:
            return False
        try:
            desc = self._pinecone_client().indexes.describe(self.config.index_name)
            dimension = int(
                getattr(desc, "dimension", 0)
                or (desc.get("dimension", 0) if isinstance(desc, dict) else 0)
            )
            metric = str(
                getattr(desc, "metric", "")
                or (desc.get("metric", "") if isinstance(desc, dict) else "")
            )
            status_payload = getattr(desc, "status", None)
            ready = bool(
                getattr(status_payload, "ready", False)
                or (
                    status_payload.get("ready", False)
                    if isinstance(status_payload, dict)
                    else False
                )
            )
            metric_is_compatible = metric == self.config.metric or (
                not self.fail_closed and metric in {"cosine", "euclidean"}
            )
            return ready and dimension == self.config.dimension and metric_is_compatible
        except Exception:
            return False

    def upsert_document(
        self,
        document: DocumentMetadata,
        version: int,
        embedded_chunks: list[EmbeddedChunk],
        batch_size: int = 100,
        publication_status: str = "draft",
        source_verification_status: str | None = None,
        legal_review_status: str = "pending",
        is_current: bool = True,
        replace_document: bool = True,
    ) -> int:
        self.ensure_index()
        index = self._pinecone_index()
        if replace_document:
            index.delete(
                namespace=self.config.namespace,
                filter={"document_id": {"$eq": document.document_id}},
            )
        vectors = [
            {
                "id": item.chunk.chunk_id,
                "values": item.embedding,
                **(
                    {
                        "sparse_values": {
                            "indices": list(item.sparse_embedding),
                            "values": list(item.sparse_embedding.values()),
                        }
                    }
                    if item.sparse_embedding
                    else {}
                ),
                "metadata": _metadata_from_embedded_chunk(
                    document,
                    version,
                    item,
                    publication_status=publication_status,
                    source_verification_status=source_verification_status,
                    legal_review_status=legal_review_status,
                    is_current=is_current,
                ),
            }
            for item in embedded_chunks
        ]
        upserted = 0
        for start in range(0, len(vectors), batch_size):
            batch = vectors[start : start + batch_size]
            response = index.upsert(vectors=batch, namespace=self.config.namespace)
            upserted += int(getattr(response, "upserted_count", len(batch)) or len(batch))
        return upserted

    def clear_namespace(self) -> None:
        """Clear only the immutable release namespace owned by this store."""
        self.ensure_index()
        self._pinecone_index().delete(
            namespace=self.config.namespace,
            delete_all=True,
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_final_score: float = 0.08,
        *,
        retrieval_query: str | None = None,
        context_topics: tuple[str, ...] = (),
        context_document_ids: tuple[str, ...] = (),
        context_articles: tuple[str, ...] = (),
    ) -> RetrievalResponse:
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
        # Query Pinecone once per rewritten query and fuse the candidates.
        # A single joined embedding dilutes distinctive rewrites (e.g. the
        # "uang kompensasi" expansion never surfaces Pasal 15 when averaged
        # with the generic phrasing), so each rewrite retrieves on its own and
        # the union is rescored downstream by lexical, fusion, and rerankers.
        rewrites = list(understanding.rewritten_queries[:3]) or [understanding.normalized_query]
        hybrid = embed_hybrid(self.embedding_provider, rewrites)
        alpha = _hybrid_alpha(understanding.normalized_query)
        # Dense and sparse vectors are evaluated together by Pinecone. Keep the
        # pre-rerank candidate pool fixed so latency and evaluation stay comparable.
        semantic_limit = 100
        query_options = {
            "top_k": semantic_limit,
            "namespace": self.config.namespace,
            "include_metadata": True,
            "include_values": False,
            "filter": _pinecone_filter(
                understanding.filters,
                allow_unpublished=self.allow_unpublished,
                include_historical=_requests_historical_sources(understanding.normalized_query),
            ),
        }
        query_options["filter"], filter_warnings = self._drop_unsupported_filter_fields(
            query_options["filter"]
        )
        sparse_query_fallback_used = False
        use_sparse = True
        matches: list[Any] = []
        for position in range(len(rewrites)):
            dense_vector = hybrid.dense[position]
            if use_sparse:
                sparse = hybrid.sparse[position]
                try:
                    response = self._pinecone_index().query(
                        vector=[value * alpha for value in dense_vector],
                        sparse_vector={
                            "indices": list(sparse),
                            "values": [value * (1 - alpha) for value in sparse.values()],
                        },
                        **query_options,
                    )
                except Exception as exc:
                    if self.fail_closed or not _index_rejects_sparse_values(exc):
                        raise
                    use_sparse = False
                    sparse_query_fallback_used = True
                    response = self._pinecone_index().query(
                        vector=dense_vector,
                        **query_options,
                    )
            else:
                response = self._pinecone_index().query(
                    vector=dense_vector,
                    **query_options,
                )
            matches.extend(list(getattr(response, "matches", []) or []))
        candidates = [_document_from_match(match) for match in matches]
        semantic_scores: dict[str, float] = {}
        for match in matches:
            score = float(getattr(match, "score", 0.0) or 0.0)
            match_id = _match_id(match)
            if score > semantic_scores.get(match_id, 0.0):
                semantic_scores[match_id] = score

        lexical_scores = {
            document.chunk_id: max(
                lexical_score(rewritten_query, document)
                for rewritten_query in understanding.rewritten_queries
            )
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
            document.chunk_id
            for document in sorted(
                candidates,
                key=lambda item: semantic_scores.get(item.chunk_id, 0.0),
                reverse=True,
            )
            if semantic_scores.get(document.chunk_id, 0.0) > 0
        ]
        fusion_scores = reciprocal_rank_fusion([lexical_ranking, semantic_ranking])
        by_id = {document.chunk_id: document for document in candidates}

        ranked: list[RankedChunk] = []
        for chunk_id in set(fusion_scores).union(semantic_scores):
            document = by_id[chunk_id]
            fusion_score = fusion_scores.get(chunk_id, 0.0)
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
        ranked = self._model_rerank(understanding.retrieval_query, ranked[:50])
        ranked = apply_relationship_adjustments(ranked, self.relationship_index)
        ranked = apply_query_focus_adjustments(
            ranked,
            understanding.normalized_retrieval_query,
        )
        ranked = drop_heading_only_chunks(ranked)
        ranked = diversify_ranked(ranked)
        selected = expand_context(ranked[:top_k], candidates)[:top_k]
        warnings = build_warnings(selected, self.relationship_index)
        warnings.extend(filter_warnings)
        if getattr(self.embedding_provider, "sparse_fallback_used", False):
            warnings.append("native_sparse_embedding_unavailable")
        if sparse_query_fallback_used:
            warnings.append("pinecone_index_requires_dotproduct")
        should_refuse = not selected or selected[0].final_score < min_final_score
        return RetrievalResponse(
            query=understanding,
            results=selected,
            warnings=warnings,
            should_refuse=should_refuse,
            refusal_reason=("no_retrieved_chunk_passed_minimum_score" if should_refuse else None),
        )

    def _model_rerank(
        self,
        query: str,
        ranked: list[RankedChunk],
    ) -> list[RankedChunk]:
        if self.reranker_provider != "pinecone" or not ranked:
            return ranked
        try:
            response = self._pinecone_client().inference.rerank(
                model=self.reranker_model,
                query=query,
                documents=[
                    {
                        "id": item.document.chunk_id,
                        "text": item.document.retrieval_text or item.document.text,
                    }
                    for item in ranked
                ],
                rank_fields=["text"],
                top_n=len(ranked),
                return_documents=False,
                parameters={"truncate": "END"},
            )
            data = list(getattr(response, "data", None) or response.get("data", []))
            reranked: list[RankedChunk] = []
            for result in data:
                index = int(
                    getattr(
                        result,
                        "index",
                        result.get("index") if isinstance(result, dict) else -1,
                    )
                )
                score = float(
                    getattr(
                        result,
                        "score",
                        result.get("score") if isinstance(result, dict) else 0,
                    )
                )
                if index < 0 or index >= len(ranked):
                    continue
                item = ranked[index]
                reranked.append(
                    replace(
                        item,
                        rerank_score=round(score, 6),
                        final_score=round((score * 0.75) + (item.final_score * 0.25), 6),
                        match_reasons=[*item.match_reasons, "cross_encoder_rerank"],
                    )
                )
            if not reranked:
                raise RuntimeError("Pinecone reranker returned no usable result.")
            return sorted(reranked, key=lambda item: item.final_score, reverse=True)
        except Exception as exc:
            if self.fail_closed:
                raise RuntimeError("Required RAG reranker is unavailable.") from exc
            return ranked

    def _pinecone_client(self):
        if self._client is None:
            try:
                from pinecone import Pinecone
            except ImportError as exc:
                raise RuntimeError("pinecone is required for VECTOR_STORE=pinecone.") from exc
            self._client = Pinecone(api_key=self.config.api_key)
        return self._client

    def _pinecone_index(self):
        if self._index is None:
            client = self._pinecone_client()
            self._index = (
                client.index(self.config.index_name)
                if hasattr(client, "index")
                else client.Index(self.config.index_name)
            )
        return self._index


def _metadata_from_embedded_chunk(
    document: DocumentMetadata,
    version: int,
    embedded_chunk: EmbeddedChunk,
    *,
    publication_status: str,
    source_verification_status: str | None,
    legal_review_status: str,
    is_current: bool,
) -> dict[str, Any]:
    chunk = embedded_chunk.chunk
    metadata = {
        "chunk_id": chunk.chunk_id,
        "document_id": document.document_id,
        "version": version,
        "title": document.title,
        "short_title": document.short_title,
        "regulation_type": document.regulation_type,
        "number": document.number,
        "year": document.year,
        "issuer": document.issuer,
        "topics": document.topics,
        "legal_status": document.legal_status,
        "verification_status": document.verification_status,
        "source_verification_status": (
            source_verification_status
            or ("verified" if document.verification_status == "verified" else "pending")
        ),
        "legal_review_status": legal_review_status,
        "publication_status": publication_status,
        "is_current": is_current,
        "source_name": document.source_name,
        "source_url": document.source_url,
        "local_file": document.local_file,
        "file_name": document.file_name,
        "embedding_model": embedded_chunk.embedding_model,
        "embedding_revision": embedded_chunk.embedding_revision,
        "build_id": chunk.build_id,
        "chapter": chunk.chapter,
        "section": chunk.section,
        "article": chunk.article,
        "paragraph": chunk.paragraph,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "token_count": chunk.token_count,
        "text": chunk.text[:PINECONE_METADATA_TEXT_LIMIT],
        "retrieval_text": (chunk.retrieval_text or chunk.text)[:PINECONE_METADATA_TEXT_LIMIT],
        "parent_text": (chunk.parent_text or "")[:PINECONE_METADATA_TEXT_LIMIT],
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _pinecone_filter(
    filters: dict[str, Any],
    *,
    allow_unpublished: bool,
    include_historical: bool,
) -> dict[str, Any] | None:
    pinecone_filter: dict[str, Any] = {}
    if article := filters.get("article"):
        pinecone_filter["article"] = {"$eq": article}
    if year := filters.get("year"):
        pinecone_filter["year"] = {"$eq": year}
    if regulation_type := filters.get("regulation_type"):
        pinecone_filter["regulation_type"] = {"$eq": regulation_type}
    if number := filters.get("number"):
        pinecone_filter["number"] = {"$eq": number}
    if legal_status := filters.get("legal_status"):
        pinecone_filter["legal_status"] = {"$eq": legal_status}
    elif not include_historical:
        pinecone_filter["legal_status"] = {"$in": ["active", "amended"]}
    if not allow_unpublished:
        pinecone_filter.update(
            {
                "publication_status": {"$eq": "published"},
                "source_verification_status": {"$eq": "verified"},
                "legal_review_status": {"$eq": "verified"},
            }
        )
        if not include_historical:
            pinecone_filter["is_current"] = {"$eq": True}
    # New index dimensions. Semantics mirror rag.indexing.filters.build_filter
    # (the canonical spec); these keys only ever exist when the query
    # explicitly asked for them — never as defaults.
    if segment_kinds := filters.get("segment_kinds"):
        pinecone_filter["segment_kind"] = {"$in": list(segment_kinds)}
    if freshness_states := filters.get("freshness_states"):
        pinecone_filter["freshness_state"] = {"$in": list(freshness_states)}
    if effective_on := filters.get("effective_on"):
        pinecone_filter["effective_date"] = {"$lte": effective_on}
    if topics := filters.get("topics"):
        pinecone_filter["topics_chunk"] = {"$in": list(topics)}
    return pinecone_filter or None


# Metadata fields backing the new filter dimensions. Old namespaces
# (schema 1) lack them: filtering on a missing field returns 0 results,
# so the store probes once per namespace and drops unsupported dimensions
# with a warning instead of silently emptying the answer.
_NEW_FILTER_FIELDS = ("segment_kind", "freshness_state", "effective_date", "topics_chunk")


def _index_rejects_sparse_values(exc: Exception) -> bool:
    message = str(exc).lower()
    return "does not support sparse values" in message or (
        "sparse values" in message and "dotproduct" in message
    )


def _document_from_match(match: Any) -> RetrievalDocument:
    metadata = _match_metadata(match)
    chunk_id = str(metadata.get("chunk_id") or _match_id(match))
    topics = metadata.get("topics", [])
    if isinstance(topics, str):
        topics = [topics]
    return RetrievalDocument(
        chunk_id=chunk_id,
        document_id=str(metadata.get("document_id", "")),
        text=str(metadata.get("text", "")),
        retrieval_text=str(metadata.get("retrieval_text") or metadata.get("text", "")),
        build_id=metadata.get("build_id"),
        chapter=metadata.get("chapter"),
        section=metadata.get("section"),
        article=metadata.get("article"),
        paragraph=metadata.get("paragraph"),
        page_start=int(metadata.get("page_start", 0) or 0),
        page_end=int(metadata.get("page_end", 0) or 0),
        token_count=int(metadata.get("token_count", 0) or 0),
        topics=list(topics),
        legal_status=str(metadata.get("legal_status", "needs_verification")),
        source_url=str(metadata.get("source_url", "")),
        embedding_model=metadata.get("embedding_model"),
        embedding=None,
        metadata={
            key: value
            for key, value in metadata.items()
            if key
            not in {
                "chunk_id",
                "document_id",
                "text",
                "retrieval_text",
                "build_id",
                "chapter",
                "section",
                "article",
                "paragraph",
                "page_start",
                "page_end",
                "token_count",
                "topics",
                "legal_status",
                "source_url",
                "embedding_model",
            }
        },
        document_version=int(metadata.get("version", 0) or 0) or None,
        publication_status=str(metadata.get("publication_status", "draft")),
        verification_status=str(metadata.get("legal_review_status", "pending")),
        is_current=bool(metadata.get("is_current", False)),
        parent_text=metadata.get("parent_text"),
        char_start=int(metadata.get("char_start", 0) or 0),
        char_end=int(metadata.get("char_end", 0) or 0),
    )


def _match_id(match: Any) -> str:
    if hasattr(match, "id"):
        return str(match.id)
    return str(match["id"])


def _match_metadata(match: Any) -> dict[str, Any]:
    if hasattr(match, "metadata"):
        return dict(match.metadata or {})
    return dict(match.get("metadata", {}))


def _hybrid_alpha(query: str) -> float:
    exact_legal_reference = re.search(
        r"\b(pasal\s+\d+[a-z]?|(?:uu|pp|permenaker|perpres)\s*(?:no\.?\s*)?\d+|"
        r"(?:19|20)\d{2})\b",
        query,
        re.IGNORECASE,
    )
    return 0.35 if exact_legal_reference else 0.65


def _requests_historical_sources(query: str) -> bool:
    return bool(
        re.search(
            r"\b(dicabut|lama|terdahulu|sebelumnya|sebelum diubah|historis|historical|"
            r"revoked|superseded|before amendment|previous version)\b",
            query,
            re.IGNORECASE,
        )
    )
