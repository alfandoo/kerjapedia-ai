from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_auth
from app.api.dependencies import get_current_user, get_db
from app.api.state import UserRecord


@pytest.fixture
def profile_env(monkeypatch):
    app = FastAPI()
    app.include_router(routes_auth.router)
    session = Mock()
    profile = SimpleNamespace(name="Old name", email="owner@example.test", roles=["user"])
    session.get.return_value = profile
    supabase = Mock()
    monkeypatch.setattr(routes_auth.supabase_service, "get_supabase", lambda: supabase)
    user = UserRecord(
        user_id="11111111-1111-4111-8111-111111111111",
        email=profile.email,
        name=profile.name,
        roles=["user"],
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: session
    return SimpleNamespace(
        app=app,
        client=TestClient(app),
        session=session,
        profile=profile,
        provider=supabase,
        user=user,
    )


def test_updates_only_authenticated_users_name(profile_env):
    env = profile_env
    response = env.client.patch("/auth/profile", json={"name": "  New name  "})
    assert response.status_code == 200
    assert response.json() == {
        "user_id": env.user.user_id,
        "email": env.user.email,
        "name": "New name",
        "roles": ["user"],
    }
    env.provider.auth.admin.update_user_by_id.assert_called_once_with(
        env.user.user_id, {"user_metadata": {"name": "New name"}}
    )
    assert env.profile.name == "New name"
    assert env.profile.roles == ["user"]
    env.session.commit.assert_called_once()


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " "},
        {"name": "x" * 81},
        {"name": "Valid", "roles": ["admin"]},
        {"name": "Valid", "user_id": "other"},
        {"name": "Valid", "email": "other@example.test"},
    ],
)
def test_rejects_invalid_or_privileged_fields(profile_env, payload):
    env = profile_env
    assert env.client.patch("/auth/profile", json=payload).status_code == 422
    env.provider.auth.admin.update_user_by_id.assert_not_called()
    env.session.commit.assert_not_called()


def test_requires_authentication(profile_env):
    env = profile_env
    env.app.dependency_overrides.pop(get_current_user)
    assert env.client.patch("/auth/profile", json={"name": "New"}).status_code == 401
    env.provider.auth.admin.update_user_by_id.assert_not_called()


def test_provider_failure_does_not_claim_saved_or_leak_error(profile_env):
    env = profile_env
    env.provider.auth.admin.update_user_by_id.side_effect = RuntimeError("secret-provider-details")
    response = env.client.patch("/auth/profile", json={"name": "New"})
    assert response.status_code == 503
    assert "secret-provider-details" not in response.text
    assert env.profile.name == "Old name"
    env.session.commit.assert_not_called()
    env.session.rollback.assert_called_once()
