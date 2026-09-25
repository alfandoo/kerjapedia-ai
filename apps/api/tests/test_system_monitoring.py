"""Offline System Monitoring tests; no database or provider calls."""

from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dependencies as deps
from app.api import routes_system_monitoring as routes
from app.services.monitoring import alerts as alert_module
from app.services.monitoring import tracing as tracing_module
from app.services.monitoring.collector import (
    classify_error,
    empty_histogram,
    histogram_percentile,
    merge_histograms,
    record_histogram_value,
)


class FakeQuery:
    def __init__(self, rows=None, scalar_value=0):
        self._rows = list(rows or [])
        self._scalar = scalar_value

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def group_by(self, *args, **kwargs):
        return self

    def distinct(self, *args, **kwargs):
        return self

    def offset(self, n):
        self._rows = self._rows[int(n or 0) :]
        return self

    def limit(self, n):
        self._rows = self._rows[: int(n)]
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def one(self):
        return self._rows[0] if self._rows else (0, 0)

    def count(self):
        return len(self._rows)

    def scalar(self):
        return self._scalar


class FakeSession:
    def __init__(self, **tables):
        self.tables = tables

    def query(self, *models):
        return FakeQuery(self.tables.get("default", []))

    def get(self, model, key):
        return (self.tables.get("by_id") or {}).get(key)

    def add(self, row):
        (self.tables.setdefault("added", [])).append(row)

    def commit(self):
        return None

    def rollback(self):
        return None

    def execute(self, *args, **kwargs):
        statement = str(args[0]) if args else ""
        if "DISTINCT ON" in statement:
            return FakeQuery([("neon_postgres", 12.0)])
        return FakeQuery([(0, None, 0)])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        deps,
        "_get_user_from_supabase",
        lambda token: NS(user_id="admin", email="a@x.io", name="A", roles=["admin"])
        if token == "admin"
        else None,
    )
    monkeypatch.setattr(
        "app.services.monitoring.probe_all_services",
        lambda: [
            {
                "service": "neon_postgres",
                "status": "healthy",
                "latency_ms": 12.0,
                "error": None,
            }
        ],
    )
    monkeypatch.setattr(
        "app.services.monitoring.record_dependency_probe", lambda **kwargs: None
    )
    monkeypatch.setattr(
        "app.services.monitoring.evaluate_alerts", lambda session: []
    )
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def _admin():
    return {"Authorization": "Bearer admin"}


# --- pure helpers ---


def test_classify_error():
    assert classify_error(200) == "ok"
    assert classify_error(429) == "rate_limited"
    assert classify_error(401) == "auth"
    assert classify_error(422) == "validation"
    assert classify_error(500) == "server"
    assert classify_error(503, "rag_temporarily_unavailable") == "provider"
    assert classify_error(504, "request_timeout") == "timeout"
    assert classify_error(None) == "unknown"


def test_histogram_percentile_approximates():
    hist = empty_histogram()
    for _ in range(90):
        record_histogram_value(hist, 80)
    for _ in range(10):
        record_histogram_value(hist, 3000)
    assert histogram_percentile(hist, 100, 0.50) == 75.0
    assert histogram_percentile(hist, 100, 0.95) == 3500.0
    assert histogram_percentile({}, 0, 0.95) is None


def test_merge_histograms_sums_buckets():
    first = empty_histogram()
    record_histogram_value(first, 10)
    merged = merge_histograms([first, {"50": 2, "+Inf": 1}])
    assert merged["50"] == 3
    assert merged["+Inf"] == 1


def test_alert_rules_fire_on_thresholds():
    active = alert_module.check_rules(
        {
            "error_rate_5m": 0.12,
            "p95_10m_ms": 4500.0,
            "services_down": ["neon_postgres"],
            "timeouts_15m": 4,
            "rate_limited_15m": 30,
        }
    )
    rules = {item["rule"] for item in active}
    assert rules == {
        "error_rate_high",
        "p95_latency_high",
        "service_down",
        "repeated_timeouts",
        "rate_limit_spike",
    }
    assert [i for i in active if i["rule"] == "error_rate_high"][0]["severity"] == (
        "critical"
    )


def test_alert_rules_quiet_when_healthy():
    assert (
        alert_module.check_rules(
            {
                "error_rate_5m": 0.001,
                "p95_10m_ms": 400.0,
                "services_down": [],
                "timeouts_15m": 0,
                "rate_limited_15m": 0,
            }
        )
        == []
    )


def test_tracing_spans_nest_with_parents():
    tracing_module.start_trace("t1", "/chat/ask")
    tracing_module.start_span("retrieval", "upstash_vector")
    tracing_module.start_span("rerank", "heuristic")
    tracing_module.end_span("ok")
    tracing_module.end_span("ok")
    finished = tracing_module.finish_trace("ok")
    assert finished is not None
    assert finished["trace_id"] == "t1"
    assert len(finished["spans"]) == 2
    assert finished["spans"][1]["parent_span_id"] == finished["spans"][0]["span_id"]
    assert all(span["duration_ms"] is not None for span in finished["spans"])


def test_tracing_persist_policy():
    assert tracing_module.should_persist("error", 10.0) is True
    assert tracing_module.should_persist("timeout", 10.0) is True
    assert tracing_module.should_persist("ok", 5000.0) is True


# --- collector fail-safe ---


def test_collector_writers_never_raise(monkeypatch):
    from app.services.monitoring import collector as collector_module

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("app.db.session.create_session", _boom)
    collector_module.record_http_request(
        route="/x", method="GET", status_code=500, latency_ms=5, error_type=None
    )
    collector_module.write_system_log(level="error", service="api", message="boom")
    collector_module.record_dependency_probe(
        service="db", status="down", latency_ms=1.0, error="down"
    )
    collector_module.record_rate_limited(route="/x")
    assert collector_module.cleanup_monitoring() == {}


# --- routes ---


def test_system_routes_require_admin(client):
    for path in (
        "/admin/system/overview",
        "/admin/system/services",
        "/admin/system/logs",
        "/admin/system/traces",
        "/admin/system/alerts",
    ):
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"Authorization": "Bearer user"})
        assert response.status_code in (401, 403)


def test_overview_shape_and_status(client, monkeypatch):
    from app.api import dependencies as deps_module

    def _factory():
        return FakeSession()

    monkeypatch.setattr(
        "app.services.monitoring.evaluate_alerts",
        lambda session: [
            {"rule": "service_down", "severity": "critical", "message": "db down"}
        ],
    )
    app = client.app
    app.dependency_overrides[deps_module.get_db] = _factory
    response = client.get("/admin/system/overview", headers=_admin())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "critical"
    assert payload["uptime_seconds"] >= 0
    assert payload["requests"]["total"] == 0
    assert payload["latency_ms"]["p95_ms"] is None
    assert payload["recent_errors"] == []
    assert payload["active_alerts"][0]["rule"] == "service_down"
    app.dependency_overrides.clear()


def test_dependency_latency_unpacks_two_column_rows():
    from app.api import routes_system_monitoring as routes_module

    class LatencySession(FakeSession):
        def execute(self, *args, **kwargs):
            return FakeQuery([("neon_postgres", 12.0)])

    result = routes_module._dependency_latency(LatencySession())
    assert result == {}


def test_logs_and_traces_lists(client, monkeypatch):
    from app.api import dependencies as deps_module

    def _fake_session():
        return FakeSession()

    app = client.app
    app.dependency_overrides[deps_module.get_db] = _fake_session
    response = client.get("/admin/system/logs", headers=_admin())
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Total-Count"] == "0"
    assert client.get("/admin/system/traces", headers=_admin()).status_code == 200
    assert client.get("/admin/system/logs/nope", headers=_admin()).status_code == 404
    assert client.get("/admin/system/traces/nope", headers=_admin()).status_code == 404
    payload = client.get("/admin/system/alerts", headers=_admin()).json()
    assert "rules" in payload and "active" in payload and "recent" in payload
    app.dependency_overrides.clear()
