"""Logout tests use only mocked Supabase clients."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from supabase_auth.errors import AuthApiError

from app.api import routes_auth as routes


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id="user-uuid"))
    monkeypatch.setattr(routes.supabase_service, "get_supabase", lambda: client)
    return client


def test_logout_revokes_using_access_jwt_not_user_id(client):
    assert routes.logout("Bearer access-jwt") == {"status": "ok"}
    client.auth.get_user.assert_called_once_with("access-jwt")
    client.auth.admin.sign_out.assert_called_once_with("access-jwt", scope="global")


@pytest.mark.parametrize("header", [None, "", "Basic secret", "Bearer "])
def test_logout_requires_bearer(client, header):
    with pytest.raises(HTTPException) as exc:
        routes.logout(header)
    assert exc.value.status_code == 401
    client.auth.admin.sign_out.assert_not_called()


def test_logout_rejects_missing_user(client):
    client.auth.get_user.return_value = SimpleNamespace(user=None)
    with pytest.raises(HTTPException) as exc:
        routes.logout("Bearer invalid")
    assert exc.value.status_code == 401
    client.auth.admin.sign_out.assert_not_called()


@pytest.mark.parametrize("operation", ["get_user", "sign_out"])
@pytest.mark.parametrize("status,expected", [(401, 401), (403, 401), (429, 503), (500, 503)])
def test_provider_failure_is_not_reported_as_success(client, operation, status, expected):
    method = client.auth.get_user if operation == "get_user" else client.auth.admin.sign_out
    method.side_effect = AuthApiError("sensitive provider detail", status, None)
    with pytest.raises(HTTPException) as exc:
        routes.logout("Bearer access-jwt")
    assert exc.value.status_code == expected
    assert "sensitive" not in exc.value.detail


def test_network_failure_returns_retryable_error(client):
    client.auth.admin.sign_out.side_effect = ConnectionError("private provider URL")
    with pytest.raises(HTTPException) as exc:
        routes.logout("Bearer access-jwt")
    assert exc.value.status_code == 503
    assert "private" not in exc.value.detail
