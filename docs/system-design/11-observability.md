# 11 — Observability

Metrics (Prometheus `app/services/telemetry.py`): HTTP latency/count/error,
chat/retrieval/Upstash/rerank/generation/verifier latency, token usage,
refusal/no-result rate, ingestion duration/failure, worker duration/retry,
RAGAS faithfulness. `/metrics` admin-only.

Tracing: `request → query understanding → retrieval → rerank → context →
generation → verification → response` dengan request/conversation/message ID,
prompt/model/release/version/chunk IDs; tanpa raw PII. OTLP endpoint
dikonfigurasi via `OTEL_EXPORTER_OTLP_ENDPOINT` + `..._INSECURE`.

Logs: structured JSON di prod (`app/core/logging.py`): timestamp, level,
service, request_id, route, latency, outcome, error_type. Audit logs
(admin login, role, upload, verification, publication, build/promote/
rollback, prompt/relationship/delete) di Neon `audit_logs`.
