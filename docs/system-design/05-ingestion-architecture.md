# 05 — Ingestion Architecture

```mermaid
sequenceDiagram
    participant AD as Admin
    participant API as FastAPI
    participant N as Neon
    participant Q as Redis Queue
    participant W as Celery Worker
    participant S as Supabase Storage
    participant V as Upstash Vector
    AD->>API: upload + validation + checksum + dedup
    API->>S: store PDF (private, storage path — bukan public URL)
    API->>N: create job/build (idempotent build_id)
    API->>Q: enqueue (Celery prod / BackgroundTasks dev)
    API-->>AD: job_id (202/queued)
    W->>W: extract, OCR fallback, parse, chunk, quality gate
    W->>N: persist metadata/chunks
    W->>V: build release candidate namespace (index-vN)
    W->>N: validate, promote active_release atomically, rollback index-vN-1
```

Idempotency: `document_id + source_checksum + pipeline_version`.
`POST /ingestion/jobs/reembed` async by default (`?sync=true` hanya admin kecil)
dan menghormati Neon governance filter.
