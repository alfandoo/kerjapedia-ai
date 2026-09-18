from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
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
    vector_store: str = "artifact"
    embedding_provider: str = "hash"
    ingestion_embedding_batch_size: int = 16
    ingestion_embedding_timeout_seconds: float = 120.0
    ingestion_embedding_max_retries: int = 3
    ingestion_embedding_retry_initial_seconds: float = 1.0
    upstash_vector_url: str = Field(
        default="",
        validation_alias=AliasChoices("upstash_vector_url", "upstash_vector_rest_url"),
    )
    upstash_vector_token: str = Field(
        default="",
        validation_alias=AliasChoices("upstash_vector_token", "upstash_vector_rest_token"),
    )
    upstash_vector_dimension: int = 1536
    upstash_vector_namespace: str = "production"
    ingestion_target_tokens: int = 350
    ingestion_max_tokens: int = 550
    ingestion_overlap_tokens: int = 60
    ingestion_min_merge_tokens: int = 180
    ingestion_parent_tokens: int = 1200
    ingestion_ocr_jobs: int = 2
    llm_provider: str = "local"
    claim_verifier_provider: str = "deterministic"
    claim_verifier_model: str = "openai/gpt-oss-120b"
    rag_fail_closed: bool = False
    rag_allow_unpublished: bool = True
    # Retrieval tuning knobs. Hybrid ranking is native to the Upstash
    # index; MMR/diversity caps and context expansion shape the final
    # candidate list after the heuristic rerank.
    retrieval_diversity_lambda: float = 0.7
    retrieval_semantic_limit: int = 100
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
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 30.0
    groq_max_retries: int = 2
    # Generous on Groq: LPU speed makes large budgets cheap, and reasoning
    # models need headroom so hidden reasoning does not starve the answer.
    groq_max_tokens: int = 6000
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
        if self.vector_store != "upstash_vector":
            raise ValueError("VECTOR_STORE must be upstash_vector in production.")
        if not self.upstash_vector_url or not self.upstash_vector_token:
            raise ValueError("UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN are required.")
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required for the OpenRouter LLM provider.")
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for the Groq LLM provider.")
        if self.llm_provider not in ("openrouter", "groq"):
            raise ValueError("LLM_PROVIDER=openrouter or groq is required in production.")
        if self.claim_verifier_provider not in ("openrouter", "groq"):
            raise ValueError(
                "CLAIM_VERIFIER_PROVIDER=openrouter or groq is required in production."
            )
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
