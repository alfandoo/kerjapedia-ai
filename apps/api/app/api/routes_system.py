from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import text

from app.api.schemas import HealthResponse
from app.core.config import settings
from app.services.providers import pinecone_store_from_settings

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    # Liveness must not depend on network services. Dependency probes belong to
    # /ready so an orchestrator can distinguish a live process from a ready one.
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
        },
    )


@router.get("/ready")
def readiness_check() -> dict:
    from app.db.session import create_session
    from app.services.retrieval.governance import load_retrieval_governance

    failures: list[str] = []
    governance = None
    try:
        with create_session() as session:
            session.execute(text("SELECT 1"))
            governance = load_retrieval_governance(
                session,
                allow_unpublished=settings.rag_allow_unpublished,
            )
    except Exception:
        failures.append("database")
    if settings.vector_store == "pinecone":
        if not pinecone_store_from_settings(settings).is_ready():
            failures.append("pinecone")
        if settings.app_env.lower() == "production" and (
            governance is None or not governance.active_namespace
        ):
            failures.append("active_rag_release")
        if settings.app_env.lower() == "production" and (
            governance is None or not governance.release_consistent
        ):
            failures.append("stale_rag_release")
    if settings.app_env.lower() == "production":
        try:
            from app.services.supabase import get_supabase

            get_supabase().table("user_profiles").select("user_id").limit(1).execute()
        except Exception:
            failures.append("supabase")
        if settings.celery_enabled:
            try:
                from redis import Redis

                Redis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                ).ping()
            except Exception:
                failures.append("redis")
    if failures:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "failures": failures},
        )
    return {"status": "ready"}


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Metrics exporter is unavailable.") from exc
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
