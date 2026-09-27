from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import routes_chat
from app.api.routes_chat import claim_guest_conversation
from app.api.state import UserRecord


class FakeSession:
    def __init__(self, conversation):
        self.conversation = conversation
        self.commits = 0

    def execute(self, _query):
        return self

    def scalar_one_or_none(self):
        return self.conversation

    def query(self, _model):
        return self

    def filter(self, _predicate):
        return self

    def count(self):
        return 2

    def commit(self):
        self.commits += 1


def user(user_id="user_one"):
    return UserRecord(user_id=user_id, email="user@example.com", name="User", roles=["user"])


def conversation(guest_id, user_id=None):
    now = datetime.now(UTC)
    return SimpleNamespace(
        conversation_id="conv_guest",
        guest_id=guest_id,
        user_id=user_id,
        title="Pertanyaan THR",
        personalized_mode=False,
        memory_summary={
            "version": 1,
            "turns": [{"source_message_id": "msg_1", "document_ids": ["thr"]}],
        },
        created_at=now,
        updated_at=now,
    )


def test_claim_transfers_guest_conversation_and_is_idempotent(monkeypatch):
    guest_id = str(uuid4())
    row = conversation(guest_id)
    session = FakeSession(row)
    transfers = []
    monkeypatch.setattr(routes_chat, "transfer_conversation", lambda *args: transfers.append(args))

    claimed = claim_guest_conversation("conv_guest", session, user(), guest_id)
    repeated = claim_guest_conversation("conv_guest", session, user(), None)

    assert claimed.conversation_id == repeated.conversation_id == "conv_guest"
    assert claimed.message_count == 2
    assert row.user_id == "user_one"
    assert row.guest_id is None
    assert row.memory_summary["turns"][0]["document_ids"] == ["thr"]
    assert session.commits == 1
    assert len(transfers) == 1


def test_claim_rejects_a_different_guest_or_account():
    guest_id = str(uuid4())
    session = FakeSession(conversation(guest_id))

    with pytest.raises(HTTPException) as wrong_guest:
        claim_guest_conversation("conv_guest", session, user(), str(uuid4()))
    assert wrong_guest.value.status_code == 403
    assert session.commits == 0

    session.conversation.user_id = "user_other"
    with pytest.raises(HTTPException) as wrong_account:
        claim_guest_conversation("conv_guest", session, user(), guest_id)
    assert wrong_account.value.status_code == 403
    assert session.commits == 0


def test_claim_requires_guest_proof_for_unclaimed_conversation():
    session = FakeSession(conversation(str(uuid4())))

    with pytest.raises(HTTPException) as missing_guest:
        claim_guest_conversation("conv_guest", session, user(), None)

    assert missing_guest.value.status_code == 400
    assert session.commits == 0
