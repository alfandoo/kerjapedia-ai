"""Lightweight dependency probes for System Monitoring.

Every probe is cheap by design: SELECT 1, index info, model list, profile
lookup, Redis ping. No PDF parsing, no vector search, and never a paid LLM
call — health checks must not cost money or load (§4).
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("kerjapedia.system")

SLOW_PROBE_MS = 2000.0
LLM_PROBE_TIMEOUT_SECONDS = 10.0


def _timed(label: str, func):
    started = time.perf_counter()
    try:
        func()
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
        reason = str(exc)[:300] or type(exc).__name__
        return {"service": label, "status": "down", "latency_ms": elapsed_ms, "error": reason}
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    if elapsed_ms > SLOW_PROBE_MS:
        return {
            "service": label,
            "status": "degraded",
            "latency_ms": elapsed_ms,
            "error": f"slow response ({elapsed_ms}ms)",
        }
    return {"service": label, "status": "healthy", "latency_ms": elapsed_ms, "error": None}


def probe_all_services() -> list[dict]:
    """Probe every real dependency; each entry has status/latency/error."""
    from app.core.config import settings

    results: list[dict] = [
        {
            "service": "application_api",
            "status": "healthy",
            "latency_ms": 0.0,
            "error": None,
        }
    ]

    def _db():
        from sqlalchemy import text

        from app.db.session import create_session

        with create_session() as session:
            session.execute(text("SELECT 1"))

    results.append(_timed("neon_postgres", _db))

    def _vector():
        from app.services.providers import upstash_vector_store_from_settings

        report = upstash_vector_store_from_settings(settings).verify_index(strict=False)
        if not report.matches_expected:
            raise RuntimeError("; ".join(report.problems) or "index mismatch")

    if settings.vector_store == "upstash_vector":
        results.append(_timed("upstash_vector", _vector))
    else:
        results.append(
            {
                "service": "upstash_vector",
                "status": "unknown",
                "latency_ms": None,
                "error": f"VECTOR_STORE={settings.vector_store}, not production hybrid",
            }
        )

    def _llm():
        import httpx

        if settings.llm_provider != "groq" or not settings.groq_api_key:
            raise RuntimeError(f"LLM_PROVIDER={settings.llm_provider}, no Groq key")
        response = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=LLM_PROBE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    if settings.app_env.lower() == "production":
        probed = _timed("groq_llm", _llm)
        if probed["status"] == "healthy" and (probed["latency_ms"] or 0) > 10000:
            probed = {**probed, "status": "degraded", "error": "slow model list"}
        results.append(probed)
    else:
        results.append(
            {
                "service": "groq_llm",
                "status": "unknown",
                "latency_ms": None,
                "error": "live LLM probe runs in production only (paid surface)",
            }
        )

    def _auth():
        from app.services.supabase import get_supabase

        get_supabase().table("user_profiles").select("user_id").limit(1).execute()

    results.append(_timed("supabase_auth", _auth))

    if settings.celery_enabled:

        def _redis():
            from redis import Redis

            Redis.from_url(
                settings.redis_url, socket_connect_timeout=2, socket_timeout=2
            ).ping()

        results.append(_timed("upstash_redis", _redis))
    else:
        results.append(
            {
                "service": "upstash_redis",
                "status": "unknown",
                "latency_ms": None,
                "error": "CELERY_ENABLED=false, queue not active",
            }
        )
    return results
