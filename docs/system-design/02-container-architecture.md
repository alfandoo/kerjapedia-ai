# 02 — Container Architecture (C4 L2)

```mermaid
flowchart TD
    user[User] --> web[Next.js Vercel<br/>chat, admin UI, proxy]
    web -->|HTTPS JSON| api[FastAPI Render kerjapedia-api<br/>auth, chat, docs, ingestion, eval, feedback]
    api --> neon[(Neon PostgreSQL<br/>users, docs, jobs, eval, audit, obs)]
    api --> storage[(Supabase Storage<br/>PDF, OCR, chunks.jsonl)]
    api --> redis[(Upstash Redis<br/>Celery queue, cache, rate-limit)]
    api --> vector[(Upstash Vector HYBRID<br/>text-embedding-3-small + BM25)]
    api --> groq[Groq<br/>generation + verifier]
    redis --> worker[Celery Worker kerjapedia-worker<br/>OCR, parsing, indexing, eval, cleanup]
    worker --> neon
    worker --> storage
    worker --> vector
    worker --> groq
    scheduler[Celery Beat kerjapedia-scheduler<br/>stale recovery, trace purge, retention] --> redis
```

Deploy: `render.yaml` memiliki `kerjapedia-api` (web), `kerjapedia-worker`
(worker), `kerjapedia-scheduler` (cron). Compose production memuat
`api/worker/scheduler/redis/postgres/migrate/web` dengan parity yang sama.
