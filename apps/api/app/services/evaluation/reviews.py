from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.business import EvaluationQuestionReview


def latest_question_reviews(
    session: Session,
    dataset_id: str,
) -> dict[str, EvaluationQuestionReview]:
    rows = (
        session.query(EvaluationQuestionReview)
        .filter(EvaluationQuestionReview.dataset_id == dataset_id)
        .order_by(
            EvaluationQuestionReview.reviewed_at.desc(),
            EvaluationQuestionReview.review_id.desc(),
        )
        .all()
    )
    latest: dict[str, EvaluationQuestionReview] = {}
    for row in rows:
        latest.setdefault(row.question_id, row)
    return latest


def verified_question_reviewers(session: Session, dataset_id: str) -> dict[str, str]:
    return {
        question_id: review.reviewer
        for question_id, review in latest_question_reviews(session, dataset_id).items()
        if review.status == "verified"
    }
