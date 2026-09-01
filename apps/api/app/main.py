from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_admin import router as admin_router
from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.api.routes_documents import router as documents_router
from app.api.routes_evaluation import router as evaluation_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_system import router as system_router
from app.api.state import state
from app.core.config import settings
from app.services.storage import ensure_bucket
from app.services.supabase import get_supabase

logger = logging.getLogger("kerjapedia.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.services.telemetry import configure_telemetry

    if settings.telemetry_enabled:
        configure_telemetry(
            settings.app_name,
            settings.otel_exporter_otlp_endpoint,
        )
    if settings.app_env.lower() != "test":
        from app.db.session import assert_schema_current

        assert_schema_current()
    if settings.app_env.lower() == "production":
        from app.db.session import create_session
        from app.services.answering.prompts import PROMPT_VERSION_ID
        from app.services.ingestion.embeddings import embed_hybrid
        from app.services.providers import (
            answer_generator_from_settings,
            embedding_provider_from_settings,
        )
        from app.services.retrieval.governance import load_retrieval_governance

        embed_hybrid(
            embedding_provider_from_settings(settings),
            ["regulasi ketenagakerjaan"],
        )
        answer_generator_from_settings(settings)

        with create_session() as session:
            governance = load_retrieval_governance(
                session,
                allow_unpublished=False,
            )
            if not governance.active_namespace:
                raise RuntimeError("Production requires an active validated RAG index release.")
            if not governance.eligible_versions:
                raise RuntimeError("Production has no published, legally reviewed documents.")
            if not governance.release_consistent:
                raise RuntimeError("The active RAG release is stale and must be replaced.")
            if governance.active_models != {
                "embedding": settings.embedding_model,
                "reranker": settings.reranker_model,
                "generator": settings.groq_model,
                "verifier": settings.claim_verifier_model,
                "prompt": PROMPT_VERSION_ID,
            }:
                raise RuntimeError(
                    "The active RAG release model provenance does not match runtime."
                )
            from app.services.providers import pinecone_store_from_settings

            if not pinecone_store_from_settings(
                settings,
                namespace=governance.active_namespace,
                relationship_index=governance.relationship_index,
                allow_unpublished=False,
            ).is_ready():
                raise RuntimeError("The production Pinecone index is not ready.")
    try:
        get_supabase()
        ensure_bucket()
    except Exception:
        logger.warning("Supabase init failed — check credentials")
        if settings.app_env.lower() == "production":
            raise
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend API for KerjaPedia AI. OpenAPI documentation is available at "
        "`/docs` and `/openapi.json`."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_and_log(request: Request, call_next):
    started_at = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    client_host = request.client.host if request.client else "unknown"
    window_seconds = 60
    limit = settings.rate_limit_per_minute
    now = time.time()

    with state.lock:
        count, window_started_at = state.request_counts.get(client_host, (0, now))
        if now - window_started_at >= window_seconds:
            count = 0
            window_started_at = now
        count += 1
        state.request_counts[client_host] = (count, window_started_at)

    if count > limit:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded."},
            headers={"X-Request-ID": request_id, "Retry-After": "60"},
        )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed request_id=%s path=%s method=%s client=%s",
            request_id,
            request.url.path,
            request.method,
            client_host,
        )
        raise

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    response.headers["X-Request-Latency-Ms"] = str(latency_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    logger.info(
        "request request_id=%s path=%s method=%s status=%s latency_ms=%s client=%s",
        request_id,
        request.url.path,
        request.method,
        response.status_code,
        latency_ms,
        client_host,
    )
    return response


app.include_router(system_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(ingestion_router)
app.include_router(evaluation_router)
app.include_router(feedback_router)
