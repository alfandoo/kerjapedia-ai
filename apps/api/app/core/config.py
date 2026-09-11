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
    pinecone_index_name: str = "kerjapedia-regulations-v2"
    pinecone_namespace: str = "production"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    embedding_provider: str = "hash"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_model_revision: str = "5617a9f61b028005a4858fdac845db406aefb181"
    ingestion_embedding_batch_size: int = 16
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
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_enabled: bool = False
    telemetry_enabled: bool = True
    otel_exporter_otlp_endpoint: str = ""
    rag_trace_retention_days: int = 30
    ragas_enabled: bool = False
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 60.0
    groq_max_retries: int = 2
    groq_max_tokens: int = 1200
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

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
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
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for the Groq LLM provider.")
        if self.vector_store != "pinecone":
            raise ValueError("VECTOR_STORE must be pinecone in production.")
        if self.pinecone_index_name != "kerjapedia-regulations-v2":
            raise ValueError(
                "Production requires PINECONE_INDEX_NAME=kerjapedia-regulations-v2."
            )
        if (
            self.embedding_provider != "bge_m3"
            or self.embedding_model.lower() != "baai/bge-m3"
        ):
            raise ValueError(
                "Production requires EMBEDDING_PROVIDER=bge_m3 and BAAI/bge-m3."
            )
        if self.embedding_dimension != 1024:
            raise ValueError(
                "Production BGE-M3 embeddings require EMBEDDING_DIMENSION=1024."
            )
        if self.embedding_model_revision in {"", "main", "unversioned"}:
            raise ValueError("Production requires a pinned EMBEDDING_MODEL_REVISION.")
        if self.llm_provider != "groq":
            raise ValueError("LLM_PROVIDER=groq is required in production.")
        if (
            self.reranker_provider != "pinecone"
            or self.reranker_model != "bge-reranker-v2-m3"
        ):
            raise ValueError(
                "Production requires Pinecone bge-reranker-v2-m3 reranking."
            )
        if self.claim_verifier_provider != "groq":
            raise ValueError("CLAIM_VERIFIER_PROVIDER=groq is required in production.")
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
