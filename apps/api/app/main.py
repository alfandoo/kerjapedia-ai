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
from app.api.routes_system_monitoring import router as system_monitoring_router
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
    from app.core.logging import configure_structured_logging
    from app.services.telemetry import configure_telemetry

    configure_structured_logging(settings.app_name, settings.app_env)
    if settings.telemetry_enabled:
        configure_telemetry(
            settings.app_name,
            settings.otel_exporter_otlp_endpoint,
            insecure=settings.otel_exporter_otlp_insecure,
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
        try:
            from app.services.ingestion.recovery import recover_stuck_ingestion_jobs

            recovered = recover_stuck_ingestion_jobs()
            if sum(recovered.values()):
                logger.info("recovered stuck ingestion jobs: %s", recovered)
        except Exception as exc:
            logger.warning("stuck ingestion recovery failed: %s", exc)
        try:
            from app.db.session import create_session
            from app.services.access import ensure_governance_seeds
            from app.services.answering.prompts import refresh_active_prompt_cache

            with create_session() as seed_session:
                seeded = ensure_governance_seeds(seed_session)
                seed_session.commit()
                active_prompt = refresh_active_prompt_cache(seed_session)
            if any(seeded.values()):
                logger.info("governance seeds ensured: %s", seeded)
            if active_prompt:
                logger.info("active prompt version: %s", active_prompt)
        except Exception as exc:
            logger.warning("governance seeding failed: %s", exc)
    if settings.app_env.lower() != "test":
        logger.info(
            "Local artifact embeddings use the deterministic hash provider; "
            "production vectors are hosted by Upstash."
        )
    if settings.app_env.lower() == "production":
        # Fail closed on the active backend: the Upstash HYBRID index must
        # exist and match the hosted-embedding contract (text-embedding-3-small
        # + BM25 + COSINE) before serving traffic. The Pinecone release system
        # was retired; document eligibility is enforced per-request instead.
        if settings.vector_store == "upstash_vector":
            from app.services.providers import upstash_vector_store_from_settings

            report = upstash_vector_store_from_settings(settings).verify_index(strict=False)
            if not report.matches_expected:
                raise RuntimeError(
                    "Upstash index does not match the hosted-embedding contract: "
                    + "; ".join(report.problems)
                )
            if report.vector_count == 0:
                raise RuntimeError("Upstash index is empty; run scripts/index_upstash.py.")
            logger.info(
                "Upstash index verified: %s vectors (dense=%s sparse=%s)",
                report.vector_count,
                report.dense_embedding_model,
                report.sparse_embedding_model,
            )
        elif settings.vector_store != "artifact":
            raise RuntimeError(
                f"Unsupported VECTOR_STORE in production: {settings.vector_store!r}."
            )
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
        incoming_id = request.headers.get("X-Request-ID") or uuid4().hex
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "detail": {
                    "code": "request_timeout",
                    "message": "The request took too long to complete.",
                }
            },
            headers={
                "X-Error-Code": "request_timeout",
                "X-Request-ID": incoming_id,
                "X-Trace-ID": incoming_id,
            },
        )


@app.middleware("http")
async def rate_limit_and_log(request: Request, call_next):
    from app.services import monitoring as sysmon

    started_at = time.perf_counter()
    # request_id and trace_id share one value so logs, traces, and errors for
    # the same request correlate with a single header round-trip.
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    trace_id = request.headers.get("X-Trace-ID") or request_id
    path = request.url.path
    if path in ("/health", "/ready", "/docs", "/openapi.json"):
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response
    headers = {key.lower(): value for key, value in request.headers.items()}
    peer_ip = request.client.host if request.client else "unknown"
    ip = client_ip(headers, peer_ip, settings.trust_proxy_headers)
    identity = client_identity(headers, peer_ip, settings.trust_proxy_headers)
    decision = rate_limiter.check(identity, ip)
    route_label = sysmon.route_template(request)

    if not decision.allowed:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        try:
            await asyncio.to_thread(
                sysmon.record_rate_limited, route=route_label
            )
            await asyncio.to_thread(
                sysmon.persist_request_observation,
                route=route_label,
                method=request.method,
                status_code=429,
                latency_ms=latency_ms,
                error_type="rate_limited",
                request_id=request_id,
                trace_id=trace_id,
                finished_trace=None,
            )
        except Exception:
            logger.debug("rate-limit observation skipped", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded."},
            headers={
                "X-Request-ID": request_id,
                "X-Trace-ID": trace_id,
                "Retry-After": str(decision.retry_after_seconds),
                "X-Error-Code": "rate_limited",
            },
        )

    sysmon.start_trace(trace_id, route_label)
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        finished = sysmon.finish_trace("error")
        logger.exception(
            "request_failed request_id=%s trace_id=%s path=%s method=%s client=%s",
            request_id,
            trace_id,
            request.url.path,
            request.method,
            identity,
        )
        try:
            await asyncio.to_thread(
                sysmon.persist_request_observation,
                route=route_label,
                method=request.method,
                status_code=500,
                latency_ms=latency_ms,
                error_type="server",
                request_id=request_id,
                trace_id=trace_id,
                finished_trace=finished,
            )
        except Exception:
            logger.debug("error observation skipped", exc_info=True)
        raise

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    error_code = response.headers.get("X-Error-Code")
    trace_status = (
        "timeout"
        if response.status_code == 504
        else ("error" if response.status_code >= 500 else "ok")
    )
    finished = sysmon.finish_trace(trace_status)
    try:
        await asyncio.to_thread(
            sysmon.persist_request_observation,
            route=route_label,
            method=request.method,
            status_code=response.status_code,
            latency_ms=latency_ms,
            error_type=error_code,
            request_id=request_id,
            trace_id=trace_id,
            finished_trace=finished,
        )
    except Exception:
        logger.debug("request observation skipped", exc_info=True)
    response.headers["X-Request-Latency-Ms"] = str(latency_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.app_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    logger.info(
        "request request_id=%s trace_id=%s path=%s method=%s status=%s latency_ms=%s client=%s",
        request_id,
        trace_id,
        request.url.path,
        request.method,
        response.status_code,
        latency_ms,
        identity,
    )
    return response


app.include_router(system_router)
app.include_router(system_monitoring_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(ingestion_router)
app.include_router(evaluation_router)
app.include_router(feedback_router)
