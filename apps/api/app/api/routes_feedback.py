from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.dependencies import AdminUser, DbSession, OptionalUser
from app.api.schemas import FeedbackRequest
from app.api.state import now_utc
from app.models.business import Feedback, Message

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _resolve_answer_id(
    session: Session,
    payload: FeedbackRequest,
) -> str | None:
    if payload.answer_id:
        return payload.answer_id
    if not payload.conversation_id:
        return None
    latest = (
        session.query(Message)
        .filter(
            Message.conversation_id == payload.conversation_id,
            Message.role == "assistant",
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    return latest.message_id if latest else None


@router.post("")
def create_feedback(
    payload: FeedbackRequest,
    session: DbSession,
    user: OptionalUser,
) -> dict:
    answer_id = _resolve_answer_id(session, payload)
    feedback = Feedback(
        feedback_id=f"fb_{uuid4().hex}",
        user_id=user.user_id if user else "anonymous",
        question=payload.question,
        answer_id=answer_id,
        conversation_id=payload.conversation_id,
        rating=payload.rating,
        issue_category=payload.issue_category,
        comment=payload.comment,
        created_at=now_utc(),
    )
    session.add(feedback)
    session.commit()
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
    rows = session.query(Feedback).order_by(Feedback.created_at.desc()).all()
    return [
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
