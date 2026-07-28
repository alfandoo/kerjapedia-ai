from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.core.config import settings
from app.services.providers import pinecone_store_from_settings
from app.services.supabase import get_supabase

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    pinecone_ready = None
    supabase_ready = False
    if settings.vector_store == "pinecone" and settings.pinecone_api_key:
        pinecone_ready = pinecone_store_from_settings(settings).is_ready()
    try:
        supabase = get_supabase()
        supabase.auth.get_user("")
        supabase_ready = True
    except Exception:
        supabase_ready = False
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        providers={
            "vector_store": settings.vector_store,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "llm_provider": settings.llm_provider,
            "groq_model": settings.groq_model if settings.llm_provider == "groq" else None,
            "pinecone_index": settings.pinecone_index_name,
            "pinecone_namespace": settings.pinecone_namespace,
            "pinecone_ready": pinecone_ready,
            "supabase_auth": supabase_ready,
        },
    )
