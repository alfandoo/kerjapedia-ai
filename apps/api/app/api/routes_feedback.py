from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from app.api.dependencies import AdminUser, OptionalUser
from app.api.schemas import FeedbackRequest
from app.api.state import now_utc, state

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
def create_feedback(
    payload: FeedbackRequest,
    user: OptionalUser,
) -> dict:
    feedback = {
        "feedback_id": f"fb_{uuid4().hex}",
        "user_id": user.user_id if user else "anonymous",
        "created_at": now_utc(),
        **payload.model_dump(),
    }
    state.feedback.append(feedback)
    return feedback


@router.get("")
def list_feedback(_: AdminUser) -> list[dict]:
    return sorted(state.feedback, key=lambda item: item["created_at"], reverse=True)
