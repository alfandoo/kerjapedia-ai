from __future__ import annotations

import time
from threading import Lock

from fastapi import APIRouter, HTTPException
from fastapi import Response as HeaderResponse
from fastapi.responses import Response
from sqlalchemy import text

from app.api.dependencies import AdminUser
from app.api.schemas import HealthResponse
from app.core.config import settings
from app.services.providers import pinecone_store_from_settings

router = APIRouter(tags=["system"])


def _embedding_sparse_flavour() -> str:
    try:
        from app.services.ingestion.embeddings import bge_native_sparse_available
    except ImportError:
        return "unknown"
    if settings.embedding_provider != "bge_m3":
        return "not_applicable"
    return "native" if bge_native_sparse_available() else "hash_fallback"


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    # Liveness must not depend on network services. Dependency probes belong to
    # /ready so an orchestrator can distinguish a live process from a ready one.
    return HealthResponse(
        status="ok",
        service=settings.app_name,
    )


_readiness_lock = Lock()
_readiness_cache: tuple[float, tuple[str, ...]] | None = None
_READINESS_TTL_SECONDS = 10


def _probe_readiness() -> list[str]:
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
        try:
            if not pinecone_store_from_settings(settings).is_ready():
                failures.append("pinecone")
        except Exception:
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
    return failures


def _readiness_failures() -> tuple[str, ...]:
    global _readiness_cache
    # Share probes across callers; public polling cannot cause parallel fan-out.
    with _readiness_lock:
        now = time.monotonic()
        if _readiness_cache is None or now >= _readiness_cache[0]:
            failures = tuple(_probe_readiness())
            _readiness_cache = (time.monotonic() + _READINESS_TTL_SECONDS, failures)
        return _readiness_cache[1]


@router.get("/ready")
def readiness_check() -> Response:
    from fastapi.responses import JSONResponse

    failed = bool(_readiness_failures())
    return JSONResponse(
        {"status": "not_ready" if failed else "ready"},
        status_code=503 if failed else 200,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/admin/system/diagnostics")
def system_diagnostics(_: AdminUser, response: HeaderResponse) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    failures = _readiness_failures()
    return {
        "status": "not_ready" if failures else "ready",
        "failures": list(failures),
        "service": settings.app_name,
        "version": settings.app_version,
        "providers": {
            "vector_store": settings.vector_store,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "embedding_sparse_flavour": _embedding_sparse_flavour(),
            "llm_provider": settings.llm_provider,
            "openrouter_model": (
                settings.openrouter_model if settings.llm_provider == "openrouter" else None
            ),
            "pinecone_index": settings.pinecone_index_name,
            "pinecone_namespace": settings.pinecone_namespace,
        },
    }


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics(_: AdminUser) -> Response:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Metrics exporter is unavailable.") from exc
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "private, no-store"},
    )
