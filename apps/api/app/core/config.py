from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "KerjaPedia AI API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    project_root: Path | None = None
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/kerjapedia"
    )
    database_connect_timeout_seconds: int = 10
    database_pool_timeout_seconds: int = 30
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""
    supabase_storage_bucket: str = "regulations"
    openai_api_key: str | None = None
    vector_store: str = "artifact"
    pinecone_api_key: str | None = None
    pinecone_index_name: str = "kerjapedia"
    pinecone_namespace: str = "production"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    embedding_provider: str = "hash"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_model_revision: str = "5617a9f61b028005a4858fdac845db406aefb181"
    ingestion_embedding_batch_size: int = 16
    ingestion_embedding_timeout_seconds: float = 120.0
    ingestion_embedding_max_retries: int = 3
    ingestion_embedding_retry_initial_seconds: float = 1.0
    pinecone_upsert_batch_size: int = 100
    pinecone_write_timeout_seconds: float = 60.0
    pinecone_write_max_retries: int = 3
    ingestion_target_tokens: int = 350
    ingestion_max_tokens: int = 550
    ingestion_overlap_tokens: int = 60
    ingestion_min_merge_tokens: int = 180
    ingestion_parent_tokens: int = 1200
    ingestion_ocr_jobs: int = 2
    llm_provider: str = "local"
    reranker_provider: str = "heuristic"
    reranker_model: str = "bge-reranker-v2-m3"
    claim_verifier_provider: str = "deterministic"
    claim_verifier_model: str = "openai/gpt-oss-120b"
    rag_fail_closed: bool = False
    rag_allow_unpublished: bool = True
    # Retrieval tuning knobs. Defaults are the calibration winners measured on
    # the golden tuning subset (2026-09): MMR lambda is insensitive at top-10
    # (0.5/0.7/0.9 identical), and hybrid alpha is a no-op against the
    # dotproduct Pinecone index (sparse queries fall back to dense-only).
    retrieval_diversity_lambda: float = 0.7
    retrieval_hybrid_alpha: float | None = None
    retrieval_semantic_limit: int = 100
    retrieval_cross_encoder_top_n: int = 50
    retrieval_cross_encoder_blend_weight: float = 0.75
    retrieval_mmr_max_per_document: int = 3
    retrieval_mmr_max_per_article: int = 2
    retrieval_expansion_max: int = 4
    retrieval_expansion_score_decay: float = 0.85
    # Context construction knobs
    max_citations: int = 4
    max_context_chunk_chars: int = 2000
    context_model_window: int = 12_000
    context_reserved_output_tokens: int = 3_000
    context_safety_margin_tokens: int = 200
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_enabled: bool = False
    telemetry_enabled: bool = True
    otel_exporter_otlp_endpoint: str = ""
    rag_trace_retention_days: int = 30
    ragas_enabled: bool = False
    ragas_sample_rate: float = 0.05
    openrouter_api_key: str | None = None
    openrouter_model: str = "openrouter/free"
    openrouter_timeout_seconds: float = 60.0
    openrouter_max_retries: int = 2
    openrouter_fallback_models: str = ""
    openrouter_transient_max_retries: int = 2
    openrouter_transient_backoff_seconds: float = 2.0
    # Measured 2026-09: with ~2.5k-token grounded prompts, gpt-oss-120b exhausts
    # 1200 completion tokens (finish_reason=length, empty content) before
    # finishing the answer+claims JSON. 3000 completes reliably.
    openrouter_max_tokens: int = 3000
    rate_limit_per_minute: int = 60
    trust_proxy_headers: bool = False
    chat_retention_days: int = 90
    session_ttl_minutes: int = 480
    admin_email: str = "admin@example.com"
    admin_password: str = "secret"
    # Fernet key (32-byte urlsafe base64) for transient signup payloads.
    # Override SECRET_KEY in production with your own generated key.
    secret_key: str = "qhWrYVGceJ9PhQQP0sKyOCFD2lFjlMQZzxg2tB1FO8s="
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender_email: str = ""
    smtp_sender_name: str = "KerjaPedia"
    smtp_use_tls: bool = True
    email_otp_expiry_minutes: int = 15
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def openrouter_fallback_model_list(self) -> list[str]:
        return [
            model.strip()
            for model in self.openrouter_fallback_models.split(",")
            if model.strip()
        ]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if not 1 <= self.ingestion_embedding_batch_size <= 64:
            raise ValueError("INGESTION_EMBEDDING_BATCH_SIZE must be between 1 and 64.")
        if self.ingestion_embedding_timeout_seconds <= 0:
            raise ValueError("INGESTION_EMBEDDING_TIMEOUT_SECONDS must be positive.")
        if self.ingestion_embedding_max_retries < 0:
            raise ValueError("INGESTION_EMBEDDING_MAX_RETRIES must not be negative.")
        if self.ingestion_embedding_retry_initial_seconds < 0:
            raise ValueError(
                "INGESTION_EMBEDDING_RETRY_INITIAL_SECONDS must not be negative."
            )
        if not 1 <= self.pinecone_upsert_batch_size <= 100:
            raise ValueError("PINECONE_UPSERT_BATCH_SIZE must be between 1 and 100.")
        if self.pinecone_write_timeout_seconds <= 0:
            raise ValueError("PINECONE_WRITE_TIMEOUT_SECONDS must be positive.")
        if self.pinecone_write_max_retries < 0:
            raise ValueError("PINECONE_WRITE_MAX_RETRIES must not be negative.")
        if self.app_env.lower() != "production":
            return self
        if self.admin_password == "secret" or len(self.admin_password) < 12:
            raise ValueError(
                "ADMIN_PASSWORD must be changed and contain at least 12 characters."
            )
        if not (
            self.supabase_url and self.supabase_service_key and self.supabase_anon_key
        ):
            raise ValueError(
                "Supabase URL, service key, and anon key are required in production."
            )
        if self.vector_store == "pinecone" and not self.pinecone_api_key:
            raise ValueError(
                "PINECONE_API_KEY is required for the Pinecone vector store."
            )
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required for the OpenRouter LLM provider.")
        if self.vector_store != "pinecone":
            raise ValueError("VECTOR_STORE must be pinecone in production.")
        if self.pinecone_index_name != "kerjapedia":
            raise ValueError(
                "Production requires PINECONE_INDEX_NAME=kerjapedia."
            )
        if (
            self.embedding_provider not in ("bge_m3", "pinecone_inference")
            or self.embedding_model.lower() not in ("baai/bge-m3", "multilingual-e5-large")
        ):
            raise ValueError(
                "Production requires EMBEDDING_PROVIDER=bge_m3 or pinecone_inference."
            )
        if self.embedding_dimension != 1024:
            raise ValueError(
                "Production BGE-M3 embeddings require EMBEDDING_DIMENSION=1024."
            )
        if (
            self.embedding_provider != "pinecone_inference"
            and self.embedding_model_revision in {"", "main", "unversioned"}
        ):
            raise ValueError("Production requires a pinned EMBEDDING_MODEL_REVISION.")
        if self.llm_provider != "openrouter":
            raise ValueError("LLM_PROVIDER=openrouter is required in production.")
        if (
            self.reranker_provider != "pinecone"
            or self.reranker_model != "bge-reranker-v2-m3"
        ):
            raise ValueError(
                "Production requires Pinecone bge-reranker-v2-m3 reranking."
            )
        if self.claim_verifier_provider != "openrouter":
            raise ValueError("CLAIM_VERIFIER_PROVIDER=openrouter is required in production.")
        if not self.claim_verifier_model:
            raise ValueError("CLAIM_VERIFIER_MODEL is required in production.")
        if not self.rag_fail_closed:
            raise ValueError("RAG_FAIL_CLOSED=true is required in production.")
        if self.rag_allow_unpublished:
            raise ValueError("RAG_ALLOW_UNPUBLISHED must be false in production.")
        if not self.celery_enabled:
            raise ValueError("CELERY_ENABLED=true is required in production.")
        if not self.redis_url:
            raise ValueError("REDIS_URL is required in production.")
        if not self.telemetry_enabled:
            raise ValueError("TELEMETRY_ENABLED=true is required in production.")
        if self.rag_trace_retention_days < 1:
            raise ValueError("RAG_TRACE_RETENTION_DAYS must be at least 1.")
        if not self.ragas_enabled:
            raise ValueError("RAGAS_ENABLED=true is required in production.")
        if any(
            "localhost" in origin or "127.0.0.1" in origin
            for origin in self.allowed_cors_origins
        ):
            raise ValueError("CORS_ORIGINS must not contain localhost in production.")
        return self

    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
