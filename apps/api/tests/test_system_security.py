"""Offline diagnostic access tests, no real provider probes or database writes."""

import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dependencies as deps
from app.api import routes_system as routes


@pytest.fixture
def env(monkeypatch):
    probe = Mock(return_value=[])
    monkeypatch.setattr(routes, "_readiness_cache", None)
    monkeypatch.setattr(routes, "_probe_readiness", probe)
    monkeypatch.setattr(
        deps,
        "_get_user_from_supabase",
        lambda token: NS(roles=[token]) if token in ("admin", "user") else None,
    )
    app = FastAPI()
    app.include_router(routes.router)
    return NS(client=TestClient(app), probe=probe)


def test_public_liveness_has_no_provider_or_version_details(env):
    response = env.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": routes.settings.app_name}
    env.probe.assert_not_called()


@pytest.mark.parametrize(
    "failures,code,expected",
    [([], 200, "ready"), (["database", "upstash_vector", "supabase"], 503, "not_ready")],
)
def test_public_readiness_only_reports_generic_status(env, failures, code, expected):
    env.probe.return_value = failures
    response = env.client.get("/ready")
    assert response.status_code == code
    assert response.json() == {"status": expected}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/metrics", "/admin/system/diagnostics"])
@pytest.mark.parametrize("token,code", [(None, 401), ("invalid", 401), ("user", 403)])
def test_diagnostics_reject_non_admin_before_work(env, path, token, code):
    headers = {"Authorization": "Bearer " + token} if token else {}
    response = env.client.get(path, headers=headers)
    assert response.status_code == code
    env.probe.assert_not_called()


def test_admin_can_read_diagnostics_without_secrets(env, monkeypatch):
    monkeypatch.setattr(routes.settings, "groq_api_key", "never-return-this-key")
    env.probe.return_value = ["database"]
    response = env.client.get(
        "/admin/system/diagnostics", headers={"Authorization": "Bearer admin"}
    )
    assert response.status_code == 200
    assert response.json()["failures"] == ["database"]
    assert "providers" in response.json()
    assert "never-return-this-key" not in response.text
    assert response.headers["cache-control"] == "private, no-store"


def test_admin_can_scrape_metrics(env, monkeypatch):
    generate = Mock(return_value=b"mock_metric 1\n")
    monkeypatch.setitem(
        sys.modules,
        "prometheus_client",
        NS(CONTENT_TYPE_LATEST="text/plain", generate_latest=generate),
    )
    response = env.client.get("/metrics", headers={"Authorization": "Bearer admin"})
    assert response.status_code == 200
    assert response.text == "mock_metric 1\n"
    assert response.headers["cache-control"] == "private, no-store"
    generate.assert_called_once()


def test_readiness_cache_shares_checks_and_refreshes_after_expiry(env, monkeypatch):
    env.client.get("/ready")
    env.client.get("/ready")
    env.client.get("/admin/system/diagnostics", headers={"Authorization": "Bearer admin"})
    env.probe.assert_called_once()
    monkeypatch.setattr(routes, "_readiness_cache", (0, ()))
    env.client.get("/ready")
    assert env.probe.call_count == 2


def test_parallel_readiness_requests_share_single_probe(env):
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: routes._readiness_failures(), range(8))) == [()] * 8
    env.probe.assert_called_once()


def test_provider_exception_is_classified_without_exposing_message(monkeypatch):
    from app.db import session as db
    from app.services.retrieval import governance

    context = Mock()
    context.__enter__ = Mock(return_value=Mock())
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(db, "create_session", lambda: context)
    monkeypatch.setattr(governance, "load_retrieval_governance", lambda *a, **kw: None)
    monkeypatch.setattr(routes.settings, "vector_store", "upstash_vector")
    monkeypatch.setattr(routes.settings, "app_env", "test")
    monkeypatch.setattr(
        "app.services.providers.upstash_vector_store_from_settings",
        Mock(side_effect=RuntimeError("private-host-and-token")),
    )
    assert routes._probe_readiness() == ["upstash_vector"]


def test_missing_exporter_is_only_reported_to_admin(env, monkeypatch):
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    assert env.client.get("/metrics").status_code == 401
    response = env.client.get("/metrics", headers={"Authorization": "Bearer admin"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Metrics exporter is unavailable."}
