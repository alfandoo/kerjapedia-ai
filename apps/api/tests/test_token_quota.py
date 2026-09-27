from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.api.routes_admin import _usage_summary
from app.core.config import settings
from app.db.session import create_session
from app.models.business import ChatTokenUsage, Conversation, DailyUsage, UserProfile
from app.services import token_quota


@pytest.fixture
def quota_rows(verify_test_schema):
    suffix = uuid4().hex
    guest_id = str(uuid4())
    guest = f"guest:{guest_id}"
    user = f"quota_{suffix}"
    conv = f"quota_conv_{suffix}"
    other = f"quota_other_{suffix}"
    with create_session() as session:
        session.add(UserProfile(user_id=user, email=f"{suffix}@example.com", name="Quota test"))
        session.add_all(
            [
                Conversation(conversation_id=conv, guest_id=guest_id, title="Quota"),
                Conversation(conversation_id=other, guest_id=guest_id, title="Other"),
            ]
        )
        session.commit()
    yield guest, user, conv, other
    with create_session() as session:
        session.execute(
            delete(ChatTokenUsage).where(ChatTokenUsage.conversation_id.in_([conv, other]))
        )
        session.execute(delete(DailyUsage).where(DailyUsage.user_key.in_([guest, user])))
        session.execute(delete(Conversation).where(Conversation.conversation_id.in_([conv, other])))
        session.execute(delete(UserProfile).where(UserProfile.user_id == user))
        session.commit()


def reserve(guest, conv, turn):
    return token_quota.reserve(
        identity_key=guest,
        conversation_id=conv,
        turn_id=turn,
        question="THR?",
        previous_messages=[],
    )


def test_provider_metering_and_replay_settle_once(quota_rows, monkeypatch):
    guest, _, conv, _ = quota_rows
    turn = uuid4().hex
    reservation = reserve(guest, conv, turn)
    assert reservation.reserved_tokens > 0
    token_quota.mark_provider_started(turn)
    token_quota.settle(turn, {"prompt_tokens": 850, "completion_tokens": 150})
    token_quota.settle(turn, {"prompt_tokens": 850, "completion_tokens": 150})
    with create_session() as session:
        result = token_quota.snapshot(guest, session)
        assert result["used_tokens"] == 1000
        assert result["estimated_tokens"] == 0
        assert result["reserved_tokens"] == 0
        assert _usage_summary(session)["today"]["provider_tokens"] >= 1000
    monkeypatch.setattr(settings, "guest_daily_token_limit", 1000)
    with pytest.raises(token_quota.QuotaExceeded):
        reserve(guest, conv, uuid4().hex)


def test_parallel_reservations_cannot_exceed_limit(quota_rows, monkeypatch):
    guest, _, conv, _ = quota_rows
    monkeypatch.setattr(settings, "guest_daily_token_limit", 7000)
    turns = [uuid4().hex for _ in range(4)]

    def attempt(turn):
        try:
            return reserve(guest, conv, turn)
        except token_quota.QuotaExceeded:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, turns))
    accepted = [item for item in results if item is not None]
    assert len(accepted) == 1
    assert accepted[0].reserved_tokens <= 7000
    with create_session() as session:
        assert token_quota.snapshot(guest, session)["reserved_tokens"] <= 7000
    token_quota.settle(turns[results.index(accepted[0])])


def test_claim_transfers_only_its_conversation_once(quota_rows):
    guest, user, conv, other = quota_rows
    for conversation in (conv, other):
        turn = uuid4().hex
        reserve(guest, conversation, turn)
        token_quota.mark_provider_started(turn)
        token_quota.settle(turn, {"prompt_tokens": 700, "completion_tokens": 300})
    with create_session() as session:
        token_quota.transfer_conversation(session, conv, guest, user)
        token_quota.transfer_conversation(session, conv, guest, user)
        session.commit()
    with create_session() as session:
        assert token_quota.snapshot(guest, session)["used_tokens"] == 1000
        account = token_quota.snapshot(user, session)
        assert account["used_tokens"] == 1000
        assert account["limit_tokens"] == 100000


def test_wib_day_changes_at_local_midnight():
    assert (
        token_quota.usage_day(datetime(2026, 9, 26, 16, 59, tzinfo=UTC)).isoformat() == "2026-09-26"
    )
    assert (
        token_quota.usage_day(datetime(2026, 9, 26, 17, 0, tzinfo=UTC)).isoformat() == "2026-09-27"
    )


def test_provider_failure_keeps_conservative_usage(quota_rows):
    guest, _, conv, _ = quota_rows
    turn = uuid4().hex
    reservation = reserve(guest, conv, turn)
    token_quota.mark_provider_started(turn)
    token_quota.settle(turn)
    with create_session() as session:
        result = token_quota.snapshot(guest, session)
        assert result["used_tokens"] == reservation.reserved_tokens
        assert result["estimated_tokens"] == reservation.reserved_tokens


def test_failure_before_provider_releases_reservation(quota_rows):
    guest, _, conv, _ = quota_rows
    turn = uuid4().hex
    reserve(guest, conv, turn)
    token_quota.settle(turn)
    with create_session() as session:
        result = token_quota.snapshot(guest, session)
        assert result["used_tokens"] == 0
        assert result["reserved_tokens"] == 0


def test_missing_provider_completion_is_estimated(quota_rows):
    guest, _, conv, _ = quota_rows
    turn = uuid4().hex
    reserve(guest, conv, turn)
    token_quota.mark_provider_started(turn)
    token_quota.settle(turn, {"prompt_tokens": 800}, "Jawaban dengan sumber.")
    with create_session() as session:
        result = token_quota.snapshot(guest, session)
        assert result["completion_tokens"] > 0
        assert result["estimated_tokens"] == result["used_tokens"]



def test_cancellation_before_provider_releases_all_reserved_tokens(quota_rows):
    guest, _, conv, _ = quota_rows
    turn = uuid4().hex
    reserve(guest, conv, turn)
    token_quota.settle(turn, cancelled=True)
    with create_session() as session:
        assert session.get(ChatTokenUsage, turn).status == "cancelled"
        result = token_quota.snapshot(guest, session)
        assert result["used_tokens"] == 0
        assert result["reserved_tokens"] == 0


def test_cancellation_after_provider_keeps_known_usage_only(quota_rows):
    guest, _, conv, _ = quota_rows
    turn = uuid4().hex
    reserve(guest, conv, turn)
    token_quota.mark_provider_started(turn)
    token_quota.settle(
        turn, {"prompt_tokens": 850, "completion_tokens": 50}, cancelled=True
    )
    with create_session() as session:
        assert session.get(ChatTokenUsage, turn).status == "cancelled"
        result = token_quota.snapshot(guest, session)
        assert result["used_tokens"] == 900
        assert result["reserved_tokens"] == 0
