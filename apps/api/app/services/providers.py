from __future__ import annotations

from threading import Lock

from app.core.config import Settings
from app.services.answering.generator import AnswerGenerator
from app.services.answering.groq_generator import GroqAnswerGenerator
from app.services.answering.openrouter_generator import OpenRouterAnswerGenerator
from app.services.ingestion.embeddings import EmbeddingProvider, build_embedding_provider
from app.services.retrieval.relationships import RelationshipIndex
from app.services.retrieval.upstash_vector_store import UpstashVectorConfig, UpstashVectorStore

_provider_lock = Lock()
_embedding_cache: dict[tuple, EmbeddingProvider] = {}
_answer_cache: dict[tuple, AnswerGenerator] = {}


def embedding_provider_from_settings(
    settings: Settings,
    provider_name: str | None = None,
) -> EmbeddingProvider:
    selected = provider_name or settings.embedding_provider
    key = (selected, settings.ingestion_embedding_batch_size)
    with _provider_lock:
        cached = _embedding_cache.get(key)
        if cached is not None:
            return cached
        provider = build_embedding_provider(provider_name=selected)
        _embedding_cache[key] = provider
        return provider


_upstash_cache: dict[tuple, UpstashVectorStore] = {}


def upstash_vector_store_from_settings(
    settings: Settings,
    *,
    relationship_index: RelationshipIndex | None = None,
    allow_unpublished: bool | None = None,
) -> UpstashVectorStore:
    if not settings.upstash_vector_url or not settings.upstash_vector_token:
        raise RuntimeError("UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN are required.")

    key = (
        settings.upstash_vector_url,
        settings.upstash_vector_dimension,
        settings.upstash_vector_namespace,
        settings.retrieval_diversity_lambda,
        allow_unpublished if allow_unpublished is not None else settings.rag_allow_unpublished,
        tuple(
            sorted(
                (k, tuple(v))
                for k, v in (
                    relationship_index.superseded_by if relationship_index else {}
                ).items()
            )
        ),
    )
    with _provider_lock:
        cached = _upstash_cache.get(key)
        if cached is not None:
            return cached

    store = UpstashVectorStore(
        config=UpstashVectorConfig(
            url=settings.upstash_vector_url,
            token=settings.upstash_vector_token,
            dimension=settings.upstash_vector_dimension,
            namespace=settings.upstash_vector_namespace,
        ),
        fail_closed=settings.rag_fail_closed,
        diversity_lambda=settings.retrieval_diversity_lambda,
        allow_unpublished=(
            allow_unpublished if allow_unpublished is not None else settings.rag_allow_unpublished
        ),
        relationship_index=relationship_index,
        semantic_limit=settings.retrieval_semantic_limit,
        mmr_max_per_document=settings.retrieval_mmr_max_per_document,
        mmr_max_per_article=settings.retrieval_mmr_max_per_article,
        expansion_max=settings.retrieval_expansion_max,
        expansion_score_decay=settings.retrieval_expansion_score_decay,
    )
    with _provider_lock:
        cached = _upstash_cache.get(key)
        if cached is not None:
            return cached
        _upstash_cache[key] = store
    return store


def answer_generator_from_settings(
    settings: Settings,
    provider_name: str | None = None,
) -> AnswerGenerator:
    llm_provider = provider_name or settings.llm_provider
    key = (
        llm_provider,
        settings.openrouter_model,
        settings.openrouter_timeout_seconds,
        settings.openrouter_max_retries,
        settings.openrouter_max_tokens,
        settings.groq_model,
        settings.groq_timeout_seconds,
        settings.groq_max_retries,
        settings.groq_max_tokens,
        settings.claim_verifier_provider,
        settings.claim_verifier_model,
        settings.rag_fail_closed,
        settings.openrouter_fallback_models,
        settings.openrouter_transient_max_retries,
        settings.openrouter_transient_backoff_seconds,
        settings.max_citations,
        settings.max_context_chunk_chars,
        settings.context_model_window,
        settings.context_reserved_output_tokens,
    )
    with _provider_lock:
        cached = _answer_cache.get(key)
        if cached is not None:
            return cached
    if llm_provider == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for LLM_PROVIDER=openrouter.")
        generator = OpenRouterAnswerGenerator(
            api_key=settings.openrouter_api_key,
            model_name=settings.openrouter_model,
            timeout_seconds=settings.openrouter_timeout_seconds,
            max_retries=settings.openrouter_max_retries,
            max_tokens=settings.openrouter_max_tokens,
            verifier_provider=settings.claim_verifier_provider,
            verifier_model=settings.claim_verifier_model,
            fail_closed=settings.rag_fail_closed,
            transient_max_retries=settings.openrouter_transient_max_retries,
            transient_backoff_seconds=settings.openrouter_transient_backoff_seconds,
            fallback_models=tuple(settings.openrouter_fallback_model_list),
            max_citations=settings.max_citations,
            max_context_chunk_chars=settings.max_context_chunk_chars,
            context_model_window=settings.context_model_window,
            context_reserved_output_tokens=settings.context_reserved_output_tokens,
            context_safety_margin_tokens=settings.context_safety_margin_tokens,
        )
    elif llm_provider == "groq":
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
            max_citations=settings.max_citations,
            max_context_chunk_chars=settings.max_context_chunk_chars,
            context_model_window=settings.context_model_window,
            context_reserved_output_tokens=settings.context_reserved_output_tokens,
            context_safety_margin_tokens=settings.context_safety_margin_tokens,
        )
    elif llm_provider == "local":
        generator = AnswerGenerator(
            max_citations=settings.max_citations,
            max_context_chunk_chars=settings.max_context_chunk_chars,
            context_model_window=settings.context_model_window,
            context_reserved_output_tokens=settings.context_reserved_output_tokens,
            context_safety_margin_tokens=settings.context_safety_margin_tokens,
        )
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
        _upstash_cache.clear()
        _answer_cache.clear()
