"""Upstash Vector retrieval store using hosted hybrid embeddings.

Active pipeline (no local embedding):

    raw chunk text --upsert--> Upstash --embed--> open-ai/text-embedding-3-small (dense)
                                                       + BM25 (sparse, hybrid index)
    raw user query --query--> Upstash hybrid search --> candidates
        --> existing heuristic rerank --> MMR/diversity --> context candidates

The application never calls ``model.encode()`` or ``openai.embeddings.create()``
on this path: dense and sparse vectors are produced server-side by Upstash.
Use :meth:`UpstashVectorStore.verify_index` (or ``scripts/index_upstash.py``)
to confirm the index is the expected HYBRID / text-embedding-3-small / BM25 /
COSINE configuration before indexing or promoting.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.services.retrieval.filtering import matches_filters
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

EXPECTED_DENSE_MODEL = "text-embedding-3-small"
EXPECTED_SPARSE_MODEL = "bm25"
EXPECTED_SIMILARITY = "cosine"
EXPECTED_DENSE_DIMENSION = 1536

UPSERT_MAX_RETRIES = 3
QUERY_MAX_RETRIES = 1
METADATA_TEXT_LIMIT = 12_000


@dataclass(frozen=True)
class UpstashVectorConfig:
    url: str
    token: str
    dimension: int = EXPECTED_DENSE_DIMENSION
    namespace: str = "production"


@dataclass(frozen=True)
class UpstashIndexReport:
    vector_count: int
    dimension: int
    similarity_function: str
    dense_embedding_model: str
    sparse_embedding_model: str
    matches_expected: bool
    problems: tuple[str, ...] = field(default_factory=tuple)


class UpstashVectorStore:
    """Hybrid retrieval backed by an Upstash-hosted embedding index."""

    def __init__(
        self,
        config: UpstashVectorConfig,
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
        upsert_max_retries: int = UPSERT_MAX_RETRIES,
        query_max_retries: int = QUERY_MAX_RETRIES,
    ) -> None:
        try:
            from upstash_vector import Index
        except ImportError as exc:
            raise RuntimeError(
                "upstash-vector is required for VECTOR_STORE=upstash_vector."
            ) from exc
        if not config.url or not config.token:
            raise RuntimeError(
                "UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN are required."
            )
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
        self.upsert_max_retries = upsert_max_retries
        self.query_max_retries = query_max_retries
        self._index = Index(url=config.url, token=config.token)

    # ------------------------------------------------------------------
    # Index verification
    # ------------------------------------------------------------------
    def verify_index(self, *, strict: bool = True) -> UpstashIndexReport:
        """Check the live index matches the hosted-embedding contract.

        Expected: HYBRID index, dense ``open-ai/text-embedding-3-small``,
        sparse ``BM25``, ``COSINE`` similarity. Raises in strict mode when
        the index does not match; otherwise returns the report with problems.
        """
        try:
            info = self._index.info()
        except Exception as exc:
            raise RuntimeError(
                "Unable to reach the Upstash Vector index. Verify "
                "UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN."
            ) from exc
        dense_model = ""
        if getattr(info, "dense_index", None) is not None:
            dense_model = str(info.dense_index.embedding_model or "")
        sparse_model = ""
        if getattr(info, "sparse_index", None) is not None:
            sparse_model = str(info.sparse_index.embedding_model or "")
        similarity = str(getattr(info, "similarity_function", "") or "")
        dimension = int(getattr(info, "dimension", 0) or 0)
        problems: list[str] = []
        if EXPECTED_DENSE_MODEL not in dense_model.lower():
            problems.append(f"dense_embedding_model={dense_model!r}")
        if EXPECTED_SPARSE_MODEL not in sparse_model.lower():
            problems.append(f"sparse_embedding_model={sparse_model!r}")
        if similarity.upper() != EXPECTED_SIMILARITY.upper():
            problems.append(f"similarity_function={similarity!r}")
        if self.config.dimension and dimension and dimension != self.config.dimension:
            problems.append(f"dimension={dimension}")
        report = UpstashIndexReport(
            vector_count=int(getattr(info, "vector_count", 0) or 0),
            dimension=dimension,
            similarity_function=similarity,
            dense_embedding_model=dense_model,
            sparse_embedding_model=sparse_model,
            matches_expected=not problems,
            problems=tuple(problems),
        )
        if strict and problems:
            raise RuntimeError(
                "Upstash index does not match the hosted-embedding contract "
                f"(expected HYBRID/{EXPECTED_DENSE_MODEL}/BM25/COSINE): "
                + "; ".join(problems)
            )
        return report

    # ------------------------------------------------------------------
    # Indexing (raw text only; Upstash embeds server-side)
    # ------------------------------------------------------------------
    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """Upsert raw-text chunks; Upstash produces dense+sparse vectors.

        Each chunk dict must have ``chunk_id`` (str), ``text`` (non-empty
        str) and optional ``metadata`` (flat dict). No dense vectors are
        ever sent: the ``data`` field carries the raw text.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if not chunks:
            return 0
        try:
            from upstash_vector.types import Vector
        except ImportError as exc:
            raise RuntimeError(
                "upstash-vector is required for VECTOR_STORE=upstash_vector."
            ) from exc
        upserted = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = [
                Vector(
                    id=chunk["chunk_id"],
                    data=chunk["text"],
                    metadata=_clean_metadata(chunk.get("metadata") or {}),
                )
                for chunk in batch
            ]
            batch_vectors = list(vectors)
            self._with_retry(
                lambda batch_vectors=batch_vectors: self._index.upsert(
                    vectors=batch_vectors, namespace=self.config.namespace
                ),
                max_retries=self.upsert_max_retries,
                operation=f"upsert batch starting at {start}",
            )
            upserted += len(batch)
        return upserted

    # ------------------------------------------------------------------
    # Retrieval (raw query text; Upstash embeds server-side)
    # ------------------------------------------------------------------
    def query(
        self,
        query_text: str,
        top_k: int = 20,
        namespace: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid search with a raw-text query (hosted dense+sparse)."""
        if not query_text or not query_text.strip():
            raise ValueError("query_text must not be empty")
        try:
            from upstash_vector.types import QueryMode
        except ImportError as exc:
            raise RuntimeError(
                "upstash-vector is required for VECTOR_STORE=upstash_vector."
            ) from exc
        target = namespace or self.config.namespace
        filter_str = build_upstash_filter(filter_metadata)
        matches = self._with_retry(
            lambda: self._index.query(
                data=query_text,
                top_k=top_k,
                include_metadata=True,
                include_data=True,
                query_mode=QueryMode.HYBRID,
                filter=filter_str,
                namespace=target,
            ),
            max_retries=self.query_max_retries,
            operation="hybrid query",
        )
        results: list[dict[str, Any]] = []
        for match in matches or []:
            if isinstance(match, dict):
                results.append(
                    {
                        "id": str(match.get("id", "")),
                        "score": float(match.get("score", 0.0) or 0.0),
                        "metadata": dict(match.get("metadata") or {}),
                        "data": match.get("data"),
                    }
                )
            else:
                results.append(
                    {
                        "id": str(match.id),
                        "score": float(match.score or 0.0),
                        "metadata": dict(match.metadata or {}),
                        "data": match.data,
                    }
                )
        return results

    def fetch_metadata(self, vector_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Read metadata for exact IDs to verify an indexing write."""
        if not vector_ids:
            return {}
        fetched = self._with_retry(
            lambda: self._index.fetch(
                ids=vector_ids,
                include_metadata=True,
                namespace=self.config.namespace,
            ),
            max_retries=self.query_max_retries,
            operation="fetch",
        )
        result: dict[str, dict[str, Any]] = {}
        for vector_id, item in zip(vector_ids, fetched or [], strict=False):
            if item is None:
                continue
            metadata = item.metadata if not isinstance(item, dict) else item.get("metadata")
            result[str(vector_id)] = dict(metadata or {})
        return result

    def namespace_vector_count(self) -> int:
        info = self._with_retry(
            lambda: self._index.info(),
            max_retries=self.query_max_retries,
            operation="index info",
        )
        namespaces = getattr(info, "namespaces", None) or {}
        entry = namespaces.get(self.config.namespace)
        if entry is None:
            return 0
        count = getattr(entry, "vector_count", None)
        if count is None and isinstance(entry, dict):
            count = entry.get("vector_count")
        if count is None:
            raise RuntimeError("Upstash index statistics omitted vector_count")
        return int(count)

    def delete_namespace(self, namespace: str | None = None) -> None:
        target = namespace or self.config.namespace
        self._with_retry(
            lambda: self._index.delete_namespace(target),
            max_retries=self.query_max_retries,
            operation=f"delete namespace {target}",
        )

    # ------------------------------------------------------------------
    # Full retrieval pipeline (shared rerank/postprocess, unchanged)
    # ------------------------------------------------------------------
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
        rerank_weights: RerankWeights | None = None,
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
        timing: dict[str, float] = {}
        t_start = time.perf_counter()
        active_rerank_weights = rerank_weights or self.rerank_weights
        rewrites = list(understanding.rewritten_queries[:3]) or [understanding.normalized_query]
        server_filter = _server_filter(
            understanding.filters,
            include_historical=_requests_historical_sources(understanding.normalized_query),
        )
        candidates: list[RetrievalDocument] = []
        seen_ids: set[str] = set()
        semantic_scores: dict[str, float] = {}
        for rewrite in rewrites:
            matches = self.query(
                rewrite, top_k=self.semantic_limit, filter_metadata=server_filter
            )
            for match in matches:
                chunk_id = match["id"]
                score = match["score"]
                if score > semantic_scores.get(chunk_id, 0.0):
                    semantic_scores[chunk_id] = score
                if chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)
                document = _document_from_match(match)
                if not self._passes_governance(document, understanding.filters):
                    continue
                candidates.append(document)
        timing["upstash_query"] = round((time.perf_counter() - t_start) * 1000, 1)

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
                lexical_scores.items(), key=lambda item: item[1], reverse=True
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
        normalized_semantic = normalize_scores(semantic_scores)

        t_rerank = time.perf_counter()
        ranked: list[RankedChunk] = []
        for chunk_id in set(fusion_scores).union(semantic_scores):
            document = by_id.get(chunk_id)
            if document is None:
                continue
            fusion_score = fusion_scores.get(chunk_id, 0.0)
            rerank, reasons = rerank_score(
                understanding,
                document,
                lexical_scores.get(chunk_id, 0.0),
                normalized_semantic.get(chunk_id, 0.0),
                fusion_score,
                weights=active_rerank_weights,
            )
            ranked.append(
                RankedChunk(
                    document=document,
                    lexical_score=round(lexical_scores.get(chunk_id, 0.0), 6),
                    semantic_score=round(normalized_semantic.get(chunk_id, 0.0), 6),
                    fusion_score=round(fusion_score, 6),
                    rerank_score=round(rerank, 6),
                    final_score=round(rerank, 6),
                    match_reasons=reasons,
                )
            )
        timing["heuristic_rerank"] = round((time.perf_counter() - t_rerank) * 1000, 1)

        t_post = time.perf_counter()
        ranked.sort(key=lambda item: item.final_score, reverse=True)
        ranked = apply_relationship_adjustments(ranked, self.relationship_index)
        ranked = apply_query_focus_adjustments(
            ranked,
            understanding.normalized_retrieval_query,
        )
        ranked = drop_heading_only_chunks(ranked)
        ranked = mmr_select(
            ranked,
            lambda_param=self.diversity_lambda,
            max_per_document=self.mmr_max_per_document,
            max_per_article=self.mmr_max_per_article,
        )
        selected = expand_context(
            ranked[:top_k],
            candidates,
            max_expansions=self.expansion_max,
            score_decay=self.expansion_score_decay,
        )[:top_k]
        timing["postprocessing"] = round((time.perf_counter() - t_post) * 1000, 1)
        timing["total_retrieval"] = round((time.perf_counter() - t_start) * 1000, 1)
        warnings = build_warnings(selected, self.relationship_index)
        should_refuse = not selected or selected[0].final_score < min_final_score
        context_metrics = {
            "candidates_count": len(candidates),
            "ranked_count": len(ranked),
            "selected_count": len(selected),
            "expansions_added": len(selected) - len(ranked[:top_k]),
        }
        return RetrievalResponse(
            query=understanding,
            results=selected,
            warnings=warnings,
            should_refuse=should_refuse,
            refusal_reason=("no_retrieved_chunk_passed_minimum_score" if should_refuse else None),
            timing=timing,
            context_metrics=context_metrics,
        )

    # ------------------------------------------------------------------
    # Governance guardrails (client-side, index-version independent)
    # ------------------------------------------------------------------
    def _passes_governance(self, document: RetrievalDocument, filters: dict[str, Any]) -> bool:
        if not matches_filters(document, filters):
            return False
        if self.allow_unpublished:
            return True
        metadata = document.metadata or {}
        return (
            document.publication_status == "published"
            and document.verification_status == "verified"
            and metadata.get("source_verification_status", "verified") == "verified"
            and document.is_current
        )

    def _with_retry(self, fn, *, max_retries: int, operation: str):
        import time as _time

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                _time.sleep(min(2**attempt, 8))
        assert last_error is not None
        raise RuntimeError(f"Upstash {operation} failed: {last_error}") from last_error


# ----------------------------------------------------------------------
# Metadata + filter helpers
# ----------------------------------------------------------------------
def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep metadata flat and bounded for the Upstash index."""
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None or isinstance(value, dict):
            continue
        if isinstance(value, str) and key in {"text", "retrieval_text", "parent_text"}:
            value = value[:METADATA_TEXT_LIMIT]
        if isinstance(value, (str, int, float, bool)):
            cleaned[str(key)] = value
        elif isinstance(value, (list, tuple)) and all(
            isinstance(item, (str, int, float, bool)) for item in value
        ):
            cleaned[str(key)] = list(value)
    return cleaned


def build_upstash_filter(filter_metadata: dict[str, Any] | None) -> str:
    """Render a scalar metadata filter to Upstash SQL-like syntax.

    ``{"year": 2021}`` -> ``"year = 2021"``;
    ``{"topics": ["pkwt", "phk"]}`` -> ``"topics IN [...]"`` is not used:
    only scalar fields are pushed server-side, list/None values are skipped
    (they are enforced client-side instead).
    """
    if not filter_metadata:
        return ""
    clauses: list[str] = []
    for key in sorted(filter_metadata):
        value = filter_metadata[key]
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue
        field = _escape_filter_identifier(str(key))
        if isinstance(value, bool):
            clauses.append(f"{field} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            clauses.append(f"{field} = {value}")
        else:
            clauses.append(f"{field} = '{_escape_filter_string(str(value))}'")
    return " AND ".join(clauses)


def _escape_filter_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe filter field: {name!r}")
    return name


def _escape_filter_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _server_filter(filters: dict[str, Any], *, include_historical: bool) -> dict[str, Any]:
    """Scalar hard filters pushed to Upstash; the rest stays client-side."""
    server: dict[str, Any] = {}
    for key in ("article", "year", "regulation_type", "number"):
        if filters.get(key) is not None:
            server[key] = filters[key]
    if filters.get("legal_status") is not None:
        server["legal_status"] = filters["legal_status"]
    elif not include_historical:
        # No IN-list support server-side; client-side governance enforces it.
        pass
    return server


def _requests_historical_sources(query: str) -> bool:
    import re

    return bool(
        re.search(
            r"\b(dicabut|lama|terdahulu|sebelumnya|sebelum diubah|historis|historical|"
            r"revoked|superseded|before amendment|previous version)\b",
            query,
            re.IGNORECASE,
        )
    )


def _document_from_match(match: dict[str, Any]) -> RetrievalDocument:
    metadata = match.get("metadata") or {}
    chunk_id = str(metadata.get("chunk_id") or match.get("id", ""))
    stored_text = str(metadata.get("text", ""))
    stored_retrieval = str(metadata.get("retrieval_text") or stored_text)
    live_data = match.get("data")
    text = str(live_data or stored_text)
    retrieval_text = str(live_data or stored_retrieval or stored_text)
    topics = metadata.get("topics", [])
    if isinstance(topics, str):
        topics = [topics]
    return RetrievalDocument(
        chunk_id=chunk_id,
        document_id=str(metadata.get("document_id", "")),
        text=text,
        retrieval_text=retrieval_text,
        build_id=metadata.get("build_id"),
        chapter=metadata.get("chapter"),
        section=metadata.get("section"),
        article=metadata.get("article"),
        paragraph=metadata.get("paragraph"),
        page_start=int(metadata.get("page_start", 0) or 0),
        page_end=int(metadata.get("page_end", 0) or metadata.get("page_start", 0) or 0),
        token_count=int(metadata.get("token_count", 0) or 0),
        topics=list(topics),
        legal_status=str(metadata.get("legal_status", "needs_verification")),
        source_url=str(metadata.get("source_url", "")),
        embedding_model=metadata.get("embedding_model", "upstash-hosted:text-embedding-3-small"),
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
        publication_status=str(metadata.get("publication_status", "published")),
        verification_status=str(
            metadata.get("legal_review_status", metadata.get("verification_status", "verified"))
        ),
        is_current=bool(metadata.get("is_current", True)),
        parent_text=metadata.get("parent_text"),
        char_start=int(metadata.get("char_start", 0) or 0),
        char_end=int(metadata.get("char_end", 0) or 0),
    )
