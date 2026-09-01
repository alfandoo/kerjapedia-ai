from __future__ import annotations

from dataclasses import replace
from threading import Lock

from app.core.config import Settings
from app.services.answering.generator import AnswerGenerator
from app.services.answering.groq_generator import GroqAnswerGenerator
from app.services.ingestion.embeddings import EmbeddingProvider, build_embedding_provider
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore
from app.services.retrieval.relationships import RelationshipIndex

_provider_lock = Lock()
_embedding_cache: dict[tuple, EmbeddingProvider] = {}
_pinecone_cache: dict[tuple, PineconeRetrievalStore] = {}
_answer_cache: dict[tuple, AnswerGenerator] = {}


def embedding_provider_from_settings(
    settings: Settings,
    provider_name: str | None = None,
    *,
    require_native_sparse: bool | None = None,
) -> EmbeddingProvider:
    selected = provider_name or settings.embedding_provider
    resolved_require_native = (
        settings.rag_fail_closed
        if require_native_sparse is None
        else require_native_sparse
    )
    key = (
        selected,
        settings.embedding_model,
        settings.embedding_dimension,
        settings.embedding_model_revision,
        settings.ingestion_embedding_batch_size,
        bool(settings.openai_api_key),
        resolved_require_native,
    )
    with _provider_lock:
        cached = _embedding_cache.get(key)
        if cached is not None:
            return cached
        provider = build_embedding_provider(
            provider_name=selected,
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimension,
            openai_api_key=settings.openai_api_key,
            require_native_sparse=resolved_require_native,
            model_revision=settings.embedding_model_revision,
            batch_size=settings.ingestion_embedding_batch_size,
        )
        _embedding_cache[key] = provider
        return provider


def pinecone_config_from_settings(settings: Settings) -> PineconeConfig:
    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is required for VECTOR_STORE=pinecone.")
    return PineconeConfig(
        api_key=settings.pinecone_api_key,
        index_name=settings.pinecone_index_name,
        namespace=settings.pinecone_namespace,
        cloud=settings.pinecone_cloud,
        region=settings.pinecone_region,
        dimension=settings.embedding_dimension,
    )


def pinecone_store_from_settings(
    settings: Settings,
    embedding_provider: EmbeddingProvider | None = None,
    *,
    namespace: str | None = None,
    relationship_index: RelationshipIndex | None = None,
    allow_unpublished: bool | None = None,
) -> PineconeRetrievalStore:
    provider = embedding_provider or embedding_provider_from_settings(settings)
    key = (
        settings.pinecone_index_name,
        namespace or settings.pinecone_namespace,
        settings.embedding_model,
        settings.embedding_dimension,
        settings.reranker_provider,
        settings.reranker_model,
        allow_unpublished if allow_unpublished is not None else settings.rag_allow_unpublished,
        tuple(
            sorted(
                (
                    key,
                    tuple(value),
                )
                for key, value in (
                    relationship_index.superseded_by if relationship_index else {}
                ).items()
            )
        ),
        id(provider),
    )
    if embedding_provider is None:
        with _provider_lock:
            cached = _pinecone_cache.get(key)
            if cached is not None:
                return cached
    store = PineconeRetrievalStore(
        config=replace(
            pinecone_config_from_settings(settings),
            namespace=namespace or settings.pinecone_namespace,
        ),
        embedding_provider=provider,
        reranker_provider=settings.reranker_provider,
        reranker_model=settings.reranker_model,
        fail_closed=settings.rag_fail_closed,
        allow_unpublished=(
            allow_unpublished if allow_unpublished is not None else settings.rag_allow_unpublished
        ),
        relationship_index=relationship_index,
    )
    if embedding_provider is None:
        with _provider_lock:
            cached = _pinecone_cache.get(key)
            if cached is not None:
                return cached
            _pinecone_cache[key] = store
    return store


def answer_generator_from_settings(
    settings: Settings,
    provider_name: str | None = None,
) -> AnswerGenerator:
    llm_provider = provider_name or settings.llm_provider
    key = (
        llm_provider,
        settings.groq_model,
        settings.groq_timeout_seconds,
        settings.groq_max_retries,
        settings.groq_max_tokens,
        settings.claim_verifier_provider,
        settings.claim_verifier_model,
        settings.rag_fail_closed,
    )
    with _provider_lock:
        cached = _answer_cache.get(key)
        if cached is not None:
            return cached
    if llm_provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required for LLM_PROVIDER=groq.")
        generator = GroqAnswerGenerator(
            api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            timeout_seconds=settings.groq_timeout_seconds,
            max_retries=settings.groq_max_retries,
            max_tokens=settings.groq_max_tokens,
            verifier_provider=settings.claim_verifier_provider,
            verifier_model=settings.claim_verifier_model,
            fail_closed=settings.rag_fail_closed,
        )
    elif llm_provider == "local":
        generator = AnswerGenerator()
    else:
        raise ValueError(f"Unsupported LLM provider: {llm_provider}")
    with _provider_lock:
        cached = _answer_cache.get(key)
        if cached is not None:
            return cached
        _answer_cache[key] = generator
    return generator


def reset_provider_caches() -> None:
    with _provider_lock:
        _embedding_cache.clear()
        _pinecone_cache.clear()
        _answer_cache.clear()
