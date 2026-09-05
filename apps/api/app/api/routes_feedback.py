from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import AdminUser, DbSession, OptionalUser
from app.api.routes_chat import _anonymous_user, _get_owned_conversation
from app.api.schemas import FeedbackRequest
from app.api.state import now_utc
from app.models.business import Feedback, Message

router = APIRouter(prefix="/feedback", tags=["feedback"])

_feedback_cache: tuple[float, list[dict]] | None = None
_FEEDBACK_CACHE_TTL = 30


def _resolve_feedback_target(session: Session, payload: FeedbackRequest, user, guest_id):
    if not payload.answer_id and not payload.conversation_id:
        return None, None, user.user_id if user else "anonymous"
    active_user = user or _anonymous_user(guest_id)
    answer = session.get(Message, payload.answer_id) if payload.answer_id else None
    if payload.answer_id and (answer is None or answer.role != "assistant"):
        raise HTTPException(status_code=404, detail="Feedback target was not found.")
    conversation_id = answer.conversation_id if answer else payload.conversation_id
    try:
        _get_owned_conversation(conversation_id, active_user, session)
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(status_code=404, detail="Feedback target was not found.") from exc
        raise
    if payload.conversation_id and payload.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="Feedback target was not found.")
    if answer is None:
        answer = (
            session.query(Message)
            .filter(Message.conversation_id == conversation_id, Message.role == "assistant")
            .order_by(Message.sequence_no.desc())
            .first()
        )
    if answer is None:
        raise HTTPException(status_code=404, detail="Feedback target was not found.")
    return answer.message_id, conversation_id, active_user.user_id


@router.post("")
def create_feedback(
    payload: FeedbackRequest,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> dict:
    global _feedback_cache
    answer_id, conversation_id, owner_id = _resolve_feedback_target(
        session, payload, user, guest_id
    )
    feedback = Feedback(
        feedback_id=f"fb_{uuid4().hex}",
        user_id=owner_id,
        question=payload.question,
        answer_id=answer_id,
        conversation_id=conversation_id,
        rating=payload.rating,
        issue_category=payload.issue_category,
        comment=payload.comment,
        created_at=now_utc(),
    )
    session.add(feedback)
    session.commit()
    _feedback_cache = None
    try:
        from app.api.routes_admin import _stats_cache

        _stats_cache.clear()
    except Exception:
        pass
    return {
        **payload.model_dump(),
        "feedback_id": feedback.feedback_id,
        "user_id": feedback.user_id,
        "answer_id": answer_id,
        "conversation_id": feedback.conversation_id,
        "created_at": feedback.created_at,
    }


@router.get("")
def list_feedback(_: AdminUser, session: DbSession) -> list[dict]:
    global _feedback_cache
    if _feedback_cache and (time.time() - _feedback_cache[0]) < _FEEDBACK_CACHE_TTL:
        return _feedback_cache[1]
    rows = session.query(Feedback).order_by(Feedback.created_at.desc()).all()
    result = [
        {
            "feedback_id": r.feedback_id,
            "user_id": r.user_id,
            "question": r.question,
            "answer_id": r.answer_id,
            "conversation_id": r.conversation_id,
            "rating": r.rating,
            "issue_category": r.issue_category,
            "comment": r.comment,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    _feedback_cache = (time.time(), result)
    return result
