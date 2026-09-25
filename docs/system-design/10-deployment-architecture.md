# 10 — Deployment Architecture

```mermaid
flowchart TD
    U[User] --> V[Vercel Next.js]
    V --> A[Render FastAPI kerjapedia-api]
    A --> N[(Neon PostgreSQL)]
    A --> Rd[(Upstash Redis)]
    A --> Vx[(Upstash Vector)]
    A --> G[Groq]
    Rd --> W[Render kerjapedia-worker<br/>celery -A app.workers.celery_app worker]
    Rd --> B[Render kerjapedia-scheduler<br/>celery beat]
    W --> N
    W --> S[(Supabase Storage)]
    A --> S
```

Health: `/health` liveness tanpa deps; `/ready` cek Neon + Upstash strict +
Supabase/Redis di prod + active release, cache 10s, 503 bila not-ready.
DB: pooled URL Neon + SSL, `pool_pre_ping`, migrasi `alembic upgrade head`
via `start.sh`/`migrate` service.
