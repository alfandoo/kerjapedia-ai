# Operational Observability Design

## Goal

Make the admin observability page useful for operating the live RAG service:
an administrator can judge current health for a defined period and identify
recent failed requests without treating all-time aggregates as live signals.

## Scope

The work applies to /admin/observability and GET /admin/metrics.

- Add fixed time windows: 24 hours, 7 days, and 30 days.
- Compute every aggregate within the selected window.
- Add a bounded, per-window metrics cache.
- Publish an explicit health/SLO summary.
- Persist a trace identifier with each request observation.
- Return a small, privacy-preserving list of recent failed requests.
- Keep the existing admin shell and visual language.

Out of scope: external alert delivery, a full tracing backend, user question
content, and arbitrary date-range queries.

## API Contract

GET /admin/metrics?window=24h|7d|30d

The default is 24h. Invalid values return FastAPI validation errors.

The response adds:

~~~
{
  "period": {
    "window": "24h",
    "starts_at": "2026-09-20T00:00:00+00:00",
    "ends_at": "2026-09-21T00:00:00+00:00"
  },
  "health": {
    "status": "healthy",
    "slo": {
      "latency_p95_seconds": { "actual": 1.2, "target": 3, "passed": true },
      "error_rate": { "actual": 0.01, "target": 0.02, "passed": true },
      "claim_support_rate": { "actual": 0.95, "target": 0.9, "passed": true }
    }
  },
  "recent_failures": [
    {
      "trace_id": "rag_...",
      "occurred_at": "2026-09-21T00:00:00+00:00",
      "outcome": "failed",
      "latency_ms": 1234,
      "topic": "pkwt"
    }
  ]
}
~~~

health.status is healthy only when every measurable SLO passes, attention
when one measurable SLO fails, and insufficient_data when no request exists
in the selected window. A missing claim-support measurement does not fail the
health status; it is reported as unavailable.

The stale frontend-only retrieved field is removed from AdminMetrics.

## Data Model And Querying

RagRequestObservation receives a nullable trace_id column and an index. New
chat completions and terminal failures write the request trace identifier.
Existing rows remain valid and show an unavailable trace identifier.

All aggregation and recent-failure queries filter created_at >= starts_at. The
endpoint caches serialized results for 30 seconds by window key. Cache
invalidation is not required because the TTL is intentionally short; the
manual reload action fetches fresh data once the TTL expires.

The selected windows are fixed rather than arbitrary to keep query patterns
index-friendly and avoid exposing a broad analytical query surface.

## Frontend Behavior

The page presents a period selector next to the reload action. Changing it
starts a new authenticated request and replaces the metrics atomically.

A compact health section explains whether the selected period meets the SLOs,
shows actual versus target values, and labels unavailable data honestly.
Recent failures are shown only when present, with UTC-derived local display
time, outcome, latency, topic, and trace ID. No question or answer text is
rendered.

The existing semantic buttons, loading state, retry state, and admin-token
redirect behavior remain intact.

## Error Handling And Privacy

The endpoint remains admin-only. A failure to load metrics keeps the existing
retry state. The dashboard does not render raw question text, answers,
citations, prompts, tokens, or user identities in its incident list.

## Verification

1. API tests prove window filtering, SLO calculation, recent-failure output,
   and unauthenticated rejection.
2. A migration test verifies the trace column and index are represented in
   Alembic.
3. Frontend tests prove the default 24-hour request, switching windows,
   reload behavior, and health/failure rendering.
4. TypeScript, lint, build, and targeted Playwright checks validate the
   rendered route.
