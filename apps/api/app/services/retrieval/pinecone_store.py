from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.ingestion.embeddings import EmbeddingProvider
from app.services.ingestion.schemas import DocumentMetadata, EmbeddedChunk
from app.services.retrieval.query import is_employment_query, understand_query
from app.services.retrieval.reranker import rerank_score
from app.services.retrieval.schemas import RankedChunk, RetrievalDocument, RetrievalResponse
from app.services.retrieval.scoring import lexical_score, reciprocal_rank_fusion

PINECONE_METADATA_TEXT_LIMIT = 12_000


@dataclass(frozen=True)
class PineconeConfig:
    api_key: str
    index_name: str = "kerjapedia-regulations"
    namespace: str = "production"
    cloud: str = "aws"
    region: str = "us-east-1"
    dimension: int = 1024
    metric: str = "cosine"


class PineconeRetrievalStore:
    def __init__(
        self,
        config: PineconeConfig,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.config = config
        self.embedding_provider = embedding_provider
        self._client = None
        self._index = None

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

    def is_ready(self) -> bool:
        if not self.config.api_key:
            return False
        try:
            desc = self._pinecone_client().indexes.describe(self.config.index_name)
            return bool(desc.status.ready)
        except Exception:
            return False

    def upsert_document(
        self,
        document: DocumentMetadata,
        version: int,
        embedded_chunks: list[EmbeddedChunk],
        batch_size: int = 100,
    ) -> int:
        self.ensure_index()
        index = self._pinecone_index()
        index.delete(
            namespace=self.config.namespace,
            filter={
                "document_id": {"$eq": document.document_id},
                "version": {"$eq": version},
            },
        )
        vectors = [
            {
                "id": item.chunk.chunk_id,
                "values": item.embedding,
                "metadata": _metadata_from_embedded_chunk(document, version, item),
            }
            for item in embedded_chunks
        ]
        upserted = 0
        for start in range(0, len(vectors), batch_size):
            batch = vectors[start : start + batch_size]
            response = index.upsert(vectors=batch, namespace=self.config.namespace)
            upserted += int(getattr(response, "upserted_count", len(batch)) or len(batch))
        return upserted

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_final_score: float = 0.08,
    ) -> RetrievalResponse:
        understanding = understand_query(query)
        if not is_employment_query(understanding):
            return RetrievalResponse(
                query=understanding,
                results=[],
                warnings=["query_outside_employment_scope"],
                should_refuse=True,
                refusal_reason="out_of_scope_query",
            )
        query_vector = self.embedding_provider.embed([" ".join(understanding.rewritten_queries)])[0]
        # Pinecone performs dense retrieval first, while lexical scoring happens
        # locally. Keep a sufficiently broad candidate pool so exact legal
        # phrases can still be recovered and promoted by the reranker.
        semantic_limit = max(top_k * 20, 100)
        response = self._pinecone_index().query(
            vector=query_vector,
            top_k=semantic_limit,
            namespace=self.config.namespace,
            include_metadata=True,
            include_values=False,
            filter=_pinecone_filter(understanding.filters),
        )
        matches = list(getattr(response, "matches", []) or [])
        candidates = [_document_from_match(match) for match in matches]
        semantic_scores = {
            _match_id(match): float(getattr(match, "score", 0.0) or 0.0) for match in matches
        }

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
        selected = ranked[:top_k]
        warnings = _warnings(selected)
        should_refuse = not selected or selected[0].final_score < min_final_score
        return RetrievalResponse(
            query=understanding,
            results=selected,
            warnings=warnings,
            should_refuse=should_refuse,
            refusal_reason=(
                "no_retrieved_chunk_passed_minimum_score" if should_refuse else None
            ),
        )

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
        "source_name": document.source_name,
        "source_url": document.source_url,
        "local_file": document.local_file,
        "file_name": document.file_name,
        "embedding_model": embedded_chunk.embedding_model,
        "chapter": chunk.chapter,
        "section": chunk.section,
        "article": chunk.article,
        "paragraph": chunk.paragraph,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "token_count": chunk.token_count,
        "text": chunk.text[:PINECONE_METADATA_TEXT_LIMIT],
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _pinecone_filter(filters: dict[str, Any]) -> dict[str, Any] | None:
    pinecone_filter: dict[str, Any] = {}
    if article := filters.get("article"):
        pinecone_filter["article"] = {"$eq": article}
    if year := filters.get("year"):
        pinecone_filter["year"] = {"$eq": year}
    if topics := filters.get("topics"):
        pinecone_filter["topics"] = {"$in": list(topics)}
    if regulation_type := filters.get("regulation_type"):
        pinecone_filter["regulation_type"] = {"$eq": regulation_type}
    if legal_status := filters.get("legal_status"):
        pinecone_filter["legal_status"] = {"$eq": legal_status}
    return pinecone_filter or None


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
    )


def _match_id(match: Any) -> str:
    if hasattr(match, "id"):
        return str(match.id)
    return str(match["id"])


def _match_metadata(match: Any) -> dict[str, Any]:
    if hasattr(match, "metadata"):
        return dict(match.metadata or {})
    return dict(match.get("metadata", {}))


def _warnings(ranked: list[RankedChunk]) -> list[str]:
    statuses = {item.document.legal_status for item in ranked}
    warnings: list[str] = []
    if "needs_verification" in statuses:
        warnings.append("retrieved_source_status_needs_verification")
    if {"revoked", "historical"}.intersection(statuses):
        warnings.append("retrieved_source_contains_historical_or_revoked_document")
    return warnings
