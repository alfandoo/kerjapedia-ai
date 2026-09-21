from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from test_api_routes import _mock_supabase_auth, admin_headers

from app.api.state import now_utc
from app.db.session import create_session
from app.main import app
from app.models.business import Conversation, DailyUsage, Message, UserProfile

pytestmark = pytest.mark.usefixtures("verify_test_schema")

_DEFAULT_GUEST_HEADERS = {"X-KerjaPedia-Guest-ID": "00000000-0000-4000-8000-000000000002"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=_DEFAULT_GUEST_HEADERS)


@pytest.fixture(autouse=True)
def clean_usage_tables() -> Iterator[None]:
    yield
    with create_session() as session:
        session.query(Message).delete()
        session.query(Conversation).delete()
        session.query(DailyUsage).delete()
        session.query(UserProfile).delete()
        session.commit()


def test_returns_zero_filled_daily_series(client: TestClient, monkeypatch) -> None:
    _mock_supabase_auth(monkeypatch, roles=["user", "admin"])
    headers = admin_headers(client)
    today = now_utc()
    yesterday = today - timedelta(days=1)
    with create_session() as session:
        session.add(Conversation(conversation_id="conv-today", title="t", created_at=today))
        session.add(
            Conversation(conversation_id="conv-yesterday", title="y", created_at=yesterday)
        )
        session.add(
            Message(
                message_id="m1",
                conversation_id="conv-today",
                role="user",
                content="q1",
                sequence_no=1,
                created_at=today,
            )
        )
        session.add(
            Message(
                message_id="m2",
                conversation_id="conv-today",
                role="user",
                content="q2",
                sequence_no=2,
                created_at=today,
            )
        )
        session.add(
            Message(
                message_id="m3",
                conversation_id="conv-today",
                role="assistant",
                content="a",
                sequence_no=3,
                created_at=today,
            )
        )
        session.add(
            Message(
                message_id="m4",
                conversation_id="conv-yesterday",
                role="user",
                content="q",
                sequence_no=1,
                created_at=yesterday,
            )
        )
        session.add(DailyUsage(user_key="u1", usage_date=today.date(), requests=3))
        session.add(DailyUsage(user_key="u2", usage_date=today.date(), requests=1))
        session.add(DailyUsage(user_key="u1", usage_date=yesterday.date(), requests=2))
        session.commit()

    response = client.get("/admin/usage/daily?days=3", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 3
    points = body["points"]
    assert len(points) == 3
    dates = [point["date"] for point in points]
    assert dates == sorted(dates)
    assert dates[-1] == today.date().isoformat()
    by_date = {point["date"]: point for point in points}
    today_point = by_date[today.date().isoformat()]
    assert today_point["messages"] == 2
    assert today_point["conversations"] == 1
    assert today_point["active_users"] == 2
    yesterday_point = by_date[yesterday.date().isoformat()]
    assert yesterday_point["messages"] == 1
    assert yesterday_point["conversations"] == 1
    assert yesterday_point["active_users"] == 1
    oldest = points[0]
    assert oldest["messages"] == 0
    assert oldest["conversations"] == 0
    assert oldest["active_users"] == 0


def test_rejects_invalid_day_range(client: TestClient, monkeypatch) -> None:
    _mock_supabase_auth(monkeypatch, roles=["user", "admin"])
    headers = admin_headers(client)

    assert client.get("/admin/usage/daily?days=0", headers=headers).status_code == 422
    assert client.get("/admin/usage/daily?days=91", headers=headers).status_code == 422


def test_requires_admin_role(client: TestClient) -> None:
    assert client.get("/admin/usage/daily").status_code in (401, 403)
