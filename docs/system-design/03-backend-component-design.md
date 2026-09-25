# 03 — Backend Component Design (FastAPI Modular Monolith)

```mermaid
flowchart TD
    MW[Middleware<br/>timeout, rate-limit, HSTS, request-id] --> R[Routers<br/>system, auth, chat, documents, ingestion, admin, evaluation, feedback]
    R --> D[Dependencies<br/>Bearer auth, RBAC admin/legal_reviewer, DbSession]
    R --> S[Domain Services]
    S --> S1[retrieval engine, governance, reranker, postprocessing]
    S --> S2[answering generator, guardrails, claim_verifier, citations]
    S --> S3[ingestion pipeline, builds, uploads, upstash_indexing]
    S --> S4[evaluation runner, ragas, tasks]
    S --> S5[calculator engine deterministic]
    S --> S6[cv_reviewer validation]
    S --> SX[storage signed-URL, telemetry, audit, rate_limit, idempotency]
    S --> DB[(Neon via SQLAlchemy session)]
```

Boundary: `app/api/*` HTTP only; `app/services/*` domain logic; `app/models/*`
Neon schema; `app/db/*` engine/session; `app/core/*` config/logging;
`app/workers/*` Celery entrypoint. Jangan duplikasi implementasi (satu
retrieval engine, satu ingestion pipeline, satu claim verifier).
