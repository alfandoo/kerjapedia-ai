from __future__ import annotations

from app.core.config import Settings
from app.services.answering.generator import AnswerGenerator
from app.services.answering.groq_generator import GroqAnswerGenerator
from app.services.ingestion.embeddings import EmbeddingProvider, build_embedding_provider
from app.services.retrieval.pinecone_store import PineconeConfig, PineconeRetrievalStore


def embedding_provider_from_settings(
    settings: Settings,
    provider_name: str | None = None,
) -> EmbeddingProvider:
    return build_embedding_provider(
        provider_name=provider_name or settings.embedding_provider,
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimension,
        openai_api_key=settings.openai_api_key,
    )


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
) -> PineconeRetrievalStore:
    provider = embedding_provider or embedding_provider_from_settings(settings)
    return PineconeRetrievalStore(
        config=pinecone_config_from_settings(settings),
        embedding_provider=provider,
    )


def answer_generator_from_settings(
    settings: Settings,
    provider_name: str | None = None,
) -> AnswerGenerator:
    llm_provider = provider_name or settings.llm_provider
    if llm_provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required for LLM_PROVIDER=groq.")
        return GroqAnswerGenerator(
            api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            timeout_seconds=settings.groq_timeout_seconds,
            max_retries=settings.groq_max_retries,
            max_tokens=settings.groq_max_tokens,
        )
    if llm_provider == "local":
        return AnswerGenerator()
    raise ValueError(f"Unsupported LLM provider: {llm_provider}")
