# 12 — Failure & Recovery (Fail-Closed)

Timeout: middleware 150s; non-stream per-stage retrieval 60s + generasi 80s
(= 140s + headroom bookkeeping), stream heartbeat 15s + budget stage yang
sama via `_pings_while`. Timeout dicatat per-stage (`timeout_retrieval` /
`timeout_generation` + provider-error counters) agar dashboard membedakan
Upstash lambat vs Groq lambat. Retry: Upstash upsert 3x, embedding batch 3x,
Celery autoretry backoff+jitter, DB advisory lock untuk ingestion.
Fail-closed: Upstash mismatch/empty, unpublished/unverified, verifier failure
→ 503/refusal, bukan silent fallback. Stale recovery: Beat hourly
(`kerjapedia.ingestion.recover_stuck` 2 jam, `kerjapedia.evaluation.fail_stuck`
3 jam) + startup lifespan + `purge_expired_traces` harian (30 hari) + chat
retention 90 hari. Recovery tidak menyentuh terminal states dan tidak
downgrade versi yang masih punya build sehat. Rollback release:
`active = index-v41` tanpa re-ingestion.
