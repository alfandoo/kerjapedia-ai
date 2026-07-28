from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "KerjaPedia AI API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    project_root: Path | None = None
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/kerjapedia"
    database_connect_timeout_seconds: int = 10
    database_pool_timeout_seconds: int = 30
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""
    supabase_storage_bucket: str = "regulations"
    openai_api_key: str | None = None
    vector_store: str = "artifact"
    pinecone_api_key: str | None = None
    pinecone_index_name: str = "kerjapedia-regulations"
    pinecone_namespace: str = "production"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    embedding_provider: str = "hash"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    llm_provider: str = "local"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 30.0
    groq_max_retries: int = 2
    groq_max_tokens: int = 1200
    rate_limit_per_minute: int = 60
    session_ttl_minutes: int = 480
    admin_email: str = "admin@example.com"
    admin_password: str = "secret"
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.app_env.lower() != "production":
            return self
        if self.admin_password == "secret" or len(self.admin_password) < 12:
            raise ValueError("ADMIN_PASSWORD must be changed and contain at least 12 characters.")
        if self.vector_store == "pinecone" and not self.pinecone_api_key:
            raise ValueError("PINECONE_API_KEY is required for the Pinecone vector store.")
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for the Groq LLM provider.")
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
