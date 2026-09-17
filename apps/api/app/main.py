from __future__ import annotations

import asyncio
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
from app.core.config import settings
from app.services.rate_limit import RateLimiter, client_identity, client_ip
from app.services.storage import ensure_bucket
from app.services.supabase import get_supabase

logger = logging.getLogger("kerjapedia.api")


class _AppState:
    """Minimal state container for test backward compatibility."""

    request_counts: dict[str, int] = {}


state = _AppState()

rate_limiter = RateLimiter(
    settings.rate_limit_per_minute, redis_url=settings.redis_url
)


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
        try:
            from app.services.evaluation.tasks import fail_stuck_runs

            reset = fail_stuck_runs()
            if reset:
                logger.info("marked %s stuck evaluation runs as failed", reset)
        except Exception as exc:
            logger.warning("stuck evaluation run reset failed: %s", exc)
    if settings.app_env.lower() != "test" and settings.embedding_provider == "bge_m3":
        # Warm both encoders at boot (torch import + ~2.3 GB model load +
        # first HF snapshot): the first user query must not pay cold start.
        # Production keeps failing fast below; elsewhere warn and continue.
        from app.services.ingestion.embeddings import embed_hybrid, embed_queries_hybrid
        from app.services.providers import embedding_provider_from_settings

        try:
            provider = embedding_provider_from_settings(settings)
            embed_hybrid(provider, ["regulasi ketenagakerjaan"])
            embed_queries_hybrid(provider, ["regulasi ketenagakerjaan"])
            logger.info("embedding warmup completed")
        except Exception as exc:
            logger.warning("embedding warmup failed: %s", exc)
            if settings.app_env.lower() == "production":
                raise
    if settings.app_env.lower() == "production":
        from app.db.session import create_session
        from app.services.answering.prompts import PROMPT_VERSION_ID
        from app.services.providers import answer_generator_from_settings
        from app.services.retrieval.governance import load_retrieval_governance

        # Embedding warmup already ran above (passage + query encoders).
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
                "generator": settings.openrouter_model,
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
async def request_timeout(request: Request, call_next):
    """Bound worker occupancy; streaming answers heartbeat instead."""
    if request.url.path == "/chat/ask/stream":
        return await call_next(request)
    try:
        return await asyncio.wait_for(call_next(request), timeout=150)
    except TimeoutError:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "detail": {
                    "code": "request_timeout",
                    "message": "The request took too long to complete.",
                }
            },
            headers={"X-Error-Code": "request_timeout"},
        )


@app.middleware("http")
async def rate_limit_and_log(request: Request, call_next):
    started_at = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    headers = {key.lower(): value for key, value in request.headers.items()}
    peer_ip = request.client.host if request.client else "unknown"
    ip = client_ip(headers, peer_ip, settings.trust_proxy_headers)
    identity = client_identity(headers, peer_ip, settings.trust_proxy_headers)
    decision = rate_limiter.check(identity, ip)

    if not decision.allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded."},
            headers={
                "X-Request-ID": request_id,
                "Retry-After": str(decision.retry_after_seconds),
                "X-Error-Code": "rate_limited",
            },
        )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed request_id=%s path=%s method=%s client=%s",
            request_id,
            request.url.path,
            request.method,
            identity,
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
        identity,
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
