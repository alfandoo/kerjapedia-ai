# Operational Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Turn the admin observability dashboard into a bounded, SLO-aware view of current RAG health with safe recent-failure drill-down.

**Architecture:** The admin API accepts one of three fixed windows, filters all database aggregates by that period, and caches the serialized response for 30 seconds per window. Durable request observations gain a trace ID so the API can return recent failures without exposing questions or answers. The frontend selects a window, renders server-derived health/SLO state, and lists only safe operational fields.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL JSONB, Alembic, Pydantic Settings, Next.js/React, shadcn Select, Playwright, pytest.

**Spec:** docs/superpowers/specs/2026-09-21-observability-operations-design.md

## Global Constraints

- Support only 24h, 7d, and 30d windows; default to 24h.
- All metrics and recent failures filter by created_at >= period start.
- Cache each window response for exactly 30 seconds.
- Do not expose question text, answers, user identities, prompts, or citations.
- Preserve the existing admin shell and visual language.
- Do not add a dependency or an external alerting service.

## Review Focus

- Invalid window values return FastAPI 422, never an unbounded query.
- Empty periods return insufficient_data rather than a misleading healthy status.
- A failed request persists its trace ID and appears in the selected time window only.
- A missing claim-support metric is shown as unavailable and does not create a false SLO failure.
- Reload and changing the period cancel stale frontend requests and never briefly show the previous period as current.

---

## File Structure

- apps/api/app/models/business.py: durable trace ID on request observations.
- apps/api/alembic/versions/20260921_0015_observability_trace_id.py: nullable column and timestamp/trace lookup index.
- apps/api/app/core/config.py: configurable SLO targets.
- apps/api/app/api/routes_chat.py: pass the existing request trace ID into durable observations.
- apps/api/app/api/routes_admin.py: fixed-window API, cached aggregation, SLO health, and safe recent failures.
- apps/api/tests/test_api_routes.py: API-level regression coverage.
- apps/web/src/features/admin/types.ts: exact response contract.
- apps/web/src/features/admin/api/index.ts: window-aware client request.
- apps/web/src/features/admin/components/admin-observability.tsx: selector, health state, and failure list.
- apps/web/tests/e2e/admin-observability.spec.ts: rendered interaction and payload coverage.

### Task 1: Persist trace IDs and expose bounded backend contract

**Files:**
- Create: apps/api/alembic/versions/20260921_0015_observability_trace_id.py
- Modify: apps/api/app/models/business.py
- Modify: apps/api/app/api/routes_chat.py
- Modify: apps/api/app/api/routes_admin.py
- Test: apps/api/tests/test_api_routes.py

**Interfaces:**
- Produces GET /admin/metrics?window=24h|7d|30d.
- Produces RagRequestObservation.trace_id: str | None.
- Produces a response with period, health, and recent_failures.

- [ ] **Step 1: Write the failing API tests for period isolation and trace drill-down**

~~~python
def test_admin_metrics_filters_window_and_returns_recent_failures(client, monkeypatch):
    _mock_supabase_auth(monkeypatch, roles=["user", "admin"])
    now = now_utc()
    with create_session() as session:
        session.add_all([
            RagRequestObservation(
                trace_id="rag_recent",
                outcome="failed",
                request_latency_ms=1200,
                topic="pkwt",
                created_at=now - timedelta(hours=1),
            ),
            RagRequestObservation(
                trace_id="rag_old",
                outcome="failed",
                request_latency_ms=900,
                topic="upah",
                created_at=now - timedelta(days=8),
            ),
        ])
        session.commit()

    payload = client.get("/admin/metrics?window=24h", headers=admin_headers(client)).json()

    assert payload["period"]["window"] == "24h"
    assert payload["requests"]["total"] == 1
    assert payload["recent_failures"][0]["trace_id"] == "rag_recent"


def test_admin_metrics_rejects_unknown_window(client, monkeypatch):
    _mock_supabase_auth(monkeypatch, roles=["user", "admin"])
    response = client.get("/admin/metrics?window=forever", headers=admin_headers(client))
    assert response.status_code == 422
~~~

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: cd apps/api; .venv/Scripts/python -m pytest tests/test_api_routes.py -k "metrics_filters_window or metrics_rejects_unknown_window" -q

Expected: FAIL because window, trace_id, and recent_failures do not exist.

- [ ] **Step 3: Add the migration and model field**

~~~python
op.add_column(
    "rag_request_observations",
    sa.Column("trace_id", sa.String(length=80), nullable=True),
)
op.create_index(
    "ix_rag_request_observations_created_at_trace_id",
    "rag_request_observations",
    ["created_at", "trace_id"],
)
~~~

~~~python
trace_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
~~~

- [ ] **Step 4: Propagate the request trace ID from both terminal chat paths**

~~~python
def _record_request_observation(
    outcome: str,
    memory=None,
    answer=None,
    latency_ms=None,
    trace_id: str | None = None,
) -> None:
    observation = RagRequestObservation(
        trace_id=trace_id[:80] if trace_id else None,
        outcome=str(outcome or "unknown")[:40],
        request_latency_ms=float(latency_ms) if latency_ms is not None else None,
    )
    observation_session.add(observation)
~~~

Pass the request-local trace_id in successful completion and exception paths; do not derive a second identifier.

- [ ] **Step 5: Implement fixed-window filtering and failure query**

~~~python
MetricWindow = Literal["24h", "7d", "30d"]
WINDOW_DELTAS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}

@router.get("/metrics")
def admin_metrics(session: DbSession, _: AdminUser, window: MetricWindow = "24h") -> dict:
    ends_at = now_utc()
    starts_at = ends_at - WINDOW_DELTAS[window]
    scoped = session.query(RagRequestObservation).filter(
        RagRequestObservation.created_at >= starts_at
    )
~~~

Use the same start condition in every aggregate. Return at most 10 newest failed observations with only trace_id, occurred_at, outcome, latency_ms, and topic.

- [ ] **Step 6: Run focused tests to verify they pass**

Run: cd apps/api; .venv/Scripts/python -m pytest tests/test_api_routes.py -k "metrics_filters_window or metrics_rejects_unknown_window or admin_metrics_persist_chat_turns" -q

Expected: PASS when the test database is available.

- [ ] **Step 7: Commit**

~~~bash
git add apps/api/alembic/versions/20260921_0015_observability_trace_id.py apps/api/app/models/business.py apps/api/app/api/routes_chat.py apps/api/app/api/routes_admin.py apps/api/tests/test_api_routes.py
git commit -m "Add bounded observability metrics"
~~~

### Task 2: Compute SLO health and cache per period

**Files:**
- Modify: apps/api/app/core/config.py
- Modify: apps/api/app/api/routes_admin.py
- Test: apps/api/tests/test_api_routes.py

**Interfaces:**
- Consumes Task 1 scoped response data.
- Produces health.status and health.slo fields.

- [ ] **Step 1: Write failing tests for SLO states and empty data**

~~~python
def test_admin_metrics_marks_breached_slo_as_attention(client, monkeypatch):
    payload = client.get("/admin/metrics?window=24h", headers=admin_headers(client)).json()
    assert payload["health"]["status"] == "attention"
    assert payload["health"]["slo"]["error_rate"]["passed"] is False


def test_admin_metrics_empty_window_is_insufficient_data(client, monkeypatch):
    _mock_supabase_auth(monkeypatch, roles=["user", "admin"])
    payload = client.get("/admin/metrics?window=24h", headers=admin_headers(client)).json()
    assert payload["health"]["status"] == "insufficient_data"
~~~

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: cd apps/api; .venv/Scripts/python -m pytest tests/test_api_routes.py -k "marks_breached_slo or empty_window_is_insufficient_data" -q

Expected: FAIL because health is absent.

- [ ] **Step 3: Add explicit, validated Settings targets**

~~~python
observability_slo_latency_p95_seconds: float = 3.0
observability_slo_error_rate: float = 0.02
observability_slo_claim_support_rate: float = 0.90
~~~

Calculate actual, target, and passed. Mark absent measurements with actual=None and passed=None.

- [ ] **Step 4: Add a 30-second cache keyed by window**

~~~python
_metrics_cache: dict[str, tuple[float, dict]] = {}
_METRICS_CACHE_TTL = 30

cached = _metrics_cache.get(window)
if cached and time.time() - cached[0] < _METRICS_CACHE_TTL:
    return cached[1]
~~~

Cache only finished responses. Never cache exceptions or authorization outcomes.

- [ ] **Step 5: Run focused tests to verify they pass**

Run: cd apps/api; .venv/Scripts/python -m pytest tests/test_api_routes.py -k "marks_breached_slo or empty_window_is_insufficient_data or metrics_filters_window" -q

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add apps/api/app/core/config.py apps/api/app/api/routes_admin.py apps/api/tests/test_api_routes.py
git commit -m "Report observability SLO health"
~~~

### Task 3: Align frontend contract and operational UI

**Files:**
- Modify: apps/web/src/features/admin/types.ts
- Modify: apps/web/src/features/admin/api/index.ts
- Modify: apps/web/src/features/admin/components/admin-observability.tsx
- Create: apps/web/tests/e2e/admin-observability.spec.ts

**Interfaces:**
- Consumes Task 1 AdminMetrics response with period, health, and recent_failures.
- Produces an accessible window selector and truthful health/failure states.

- [ ] **Step 1: Write failing Playwright coverage for window selection**

~~~ts
await page.getByRole("combobox", { name: "Periode metrik" }).selectOption("7d");
await expect.poll(() => metricsRequests.at(-1)?.url()).toContain("window=7d");
await expect(page.getByText("Perlu perhatian")).toBeVisible();
await expect(page.getByText("rag_recent")).toBeVisible();
~~~

Mock auth/session and admin/metrics; record each request URL. Include an empty 24h response and a breached 7d response.

- [ ] **Step 2: Run the test to verify it fails**

Run: cd apps/web; npx playwright test tests/e2e/admin-observability.spec.ts

Expected: FAIL because there is no period combobox or health/failure output.

- [ ] **Step 3: Align TypeScript and API client**

~~~ts
export type MetricsWindow = "24h" | "7d" | "30d";

export type AdminMetrics = {
  period: { window: MetricsWindow; starts_at: string; ends_at: string };
  health: { status: "healthy" | "attention" | "insufficient_data"; slo: Record<string, SloMetric> };
  recent_failures: RecentFailure[];
  // existing fields, without retrieved
};
~~~

Make fetchAdminMetrics(window, signal) append ?window= to the authenticated request.

- [ ] **Step 4: Implement selector, health summary, and recent failures**

Use existing Select, SelectTrigger, SelectContent, and SelectItem components. Put health before broad metrics because the admin's first decision is whether action is required. Show failures only when actual failures exist. Use semantic section, dl, dt, dd, and an aria-live="polite" period status. Preserve abort-controller cleanup so a slower prior-period response cannot overwrite a newer selection.

- [ ] **Step 5: Run E2E test to verify it passes**

Run: cd apps/web; npx playwright test tests/e2e/admin-observability.spec.ts

Expected: PASS with a 24h initial request, a 7d switched request, and rendered SLO/failure details.

- [ ] **Step 6: Commit**

~~~bash
git add apps/web/src/features/admin/types.ts apps/web/src/features/admin/api/index.ts apps/web/src/features/admin/components/admin-observability.tsx apps/web/tests/e2e/admin-observability.spec.ts
git commit -m "Add operational observability controls"
~~~

### Task 4: Verify migration, contracts, and rendered behavior

**Files:**
- Modify: apps/api/tests/test_api_routes.py only if a verification gap is found.
- Modify: apps/web/tests/e2e/admin-observability.spec.ts only if a verification gap is found.

**Interfaces:**
- Consumes the finished API contract and UI from Tasks 1-3.
- Produces evidence that no broad query, stale contract, or inaccessible control remains.

- [ ] **Step 1: Add review-focus tests**

~~~python
def test_admin_metrics_missing_claims_keeps_health_measurement_unavailable(client, monkeypatch):
    _mock_supabase_auth(monkeypatch, roles=["user", "admin"])
    payload = client.get("/admin/metrics?window=24h", headers=admin_headers(client)).json()
    assert payload["health"]["slo"]["claim_support_rate"]["passed"] is None
~~~

~~~ts
await page.getByRole("button", { name: "Muat ulang" }).click();
await expect.poll(() => metricsRequests.length).toBeGreaterThan(initialRequestCount);
~~~

- [ ] **Step 2: Run backend and frontend focused suites**

Run: cd apps/api; .venv/Scripts/python -m pytest tests/test_api_routes.py -k metrics -q

Run: cd apps/web; npx playwright test tests/e2e/admin-observability.spec.ts

Expected: PASS. If the known local test database is unavailable, record the exact connection blocker and still run lint/type checks.

- [ ] **Step 3: Run static verification**

Run: cd apps/api; .venv/Scripts/python -m ruff check app tests

Run: cd apps/web; npx tsc --noEmit --incremental false

Run: cd apps/web; npx eslint src/features/admin/components/admin-observability.tsx tests/e2e/admin-observability.spec.ts

Run: git diff --check

Expected: all commands exit 0.

- [ ] **Step 4: Commit verification adjustments**

~~~bash
git add apps/api/tests/test_api_routes.py apps/web/tests/e2e/admin-observability.spec.ts
git commit -m "Verify observability operations flow"
~~~
