"""Offline feedback ownership tests; no database or provider connections."""

from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.api.routes_feedback import create_feedback
from app.api.schemas import FeedbackRequest
from app.models.business import Conversation, Message

GUEST = "11111111-1111-4111-8111-111111111111"
OTHER_GUEST = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def data():
    conversation = NS(conversation_id="conv", user_id="owner", guest_id=None)
    answer = NS(message_id="answer", conversation_id="conv", role="assistant")
    session = Mock()
    session.get.side_effect = lambda model, key: (
        conversation
        if model is Conversation and key == "conv"
        else answer
        if model is Message and key == "answer"
        else None
    )
    session.query.return_value.filter.return_value.order_by.return_value.first.return_value = answer
    return NS(session=session, conversation=conversation, answer=answer)


def submit(data, user="owner", guest=None, **fields):
    payload = FeedbackRequest(question="Test question", rating="helpful", **fields)
    return create_feedback(
        payload, data.session, NS(user_id=user, roles=["admin"]) if user else None, guest
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"answer_id": "answer"},
        {"conversation_id": "conv"},
        {"answer_id": "answer", "conversation_id": "conv"},
    ],
)
def test_owner_can_submit_and_ids_are_resolved(data, fields):
    result = submit(data, **fields)
    assert result["answer_id"] == "answer"
    assert result["conversation_id"] == "conv"
    assert result["user_id"] == "owner"
    data.session.commit.assert_called_once()


@pytest.mark.parametrize(
    "fields",
    [
        {"answer_id": "answer"},
        {"conversation_id": "conv"},
        {"answer_id": "answer", "conversation_id": "conv"},
    ],
)
def test_other_user_including_admin_cannot_target_conversation(data, fields):
    with pytest.raises(HTTPException) as exc:
        submit(data, user="attacker", **fields)
    assert exc.value.status_code == 404
    data.session.add.assert_not_called()
    data.session.commit.assert_not_called()


@pytest.mark.parametrize(
    "fields",
    [
        {"answer_id": "missing"},
        {"conversation_id": "missing"},
        {"answer_id": "answer", "conversation_id": "different"},
    ],
)
def test_unknown_or_mismatched_target_is_rejected(data, fields):
    with pytest.raises(HTTPException) as exc:
        submit(data, **fields)
    assert exc.value.status_code == 404
    data.session.commit.assert_not_called()


def test_user_message_is_not_an_answer(data):
    data.answer.role = "user"
    with pytest.raises(HTTPException):
        submit(data, answer_id="answer")
    data.session.commit.assert_not_called()


@pytest.mark.parametrize(
    "guest,expected", [(GUEST, 200), (OTHER_GUEST, 404), (None, 400), ("invalid", 400)]
)
def test_guest_must_own_conversation(data, guest, expected):
    data.conversation.user_id = None
    data.conversation.guest_id = GUEST
    if expected == 200:
        result = submit(data, user=None, guest=guest, answer_id="answer")
        assert result["user_id"] == "guest:" + GUEST
    else:
        with pytest.raises(HTTPException) as exc:
            submit(data, user=None, guest=guest, answer_id="answer")
        assert exc.value.status_code == expected
        data.session.commit.assert_not_called()


def test_signed_in_user_cannot_claim_guest_ownership_via_header(data):
    data.conversation.user_id = None
    data.conversation.guest_id = GUEST
    with pytest.raises(HTTPException):
        submit(data, guest=GUEST, answer_id="answer")
    data.session.commit.assert_not_called()


def test_legacy_unowned_conversation_rejected(data):
    data.conversation.user_id = None
    with pytest.raises(HTTPException):
        submit(data, user=None, guest=GUEST, answer_id="answer")
    data.session.commit.assert_not_called()


def test_conversation_without_assistant_answer_rejected(data):
    data.session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        None
    )
    with pytest.raises(HTTPException):
        submit(data, conversation_id="conv")
    data.session.commit.assert_not_called()


def test_general_feedback_remains_unlinked(data):
    result = submit(data, user=None)
    assert result["answer_id"] is None
    assert result["conversation_id"] is None
    assert result["user_id"] == "anonymous"
