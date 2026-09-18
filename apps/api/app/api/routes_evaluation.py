from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.dependencies import AdminUser, DbSession, LegalReviewerUser
from app.api.schemas import (
    EvaluationDatasetRequest,
    EvaluationQuestionReviewRequest,
    EvaluationRunRequest,
)
from app.api.state import now_utc
from app.api.utils import project_root
from app.models.business import EvaluationDataset, EvaluationQuestionReview, EvaluationRun
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.schemas import EvaluationQuestion
from app.services.evaluation.tasks import execute_evaluation_run

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/datasets")
def create_evaluation_dataset(
    payload: EvaluationDatasetRequest,
    session: DbSession,
    _: AdminUser,
) -> dict:
    dataset_id = f"evalset_{uuid4().hex}"
    dataset = EvaluationDataset(
        dataset_id=dataset_id,
        name=payload.name,
        questions=[
            {
                **question.model_dump(),
                "verified_by": "unknown",
                "status": "needs_human_review",
            }
            for question in payload.questions
        ],
        created_at=now_utc(),
    )
    session.add(dataset)
    session.commit()
    return {
        "dataset_id": dataset_id,
        "name": payload.name,
        "questions": dataset.questions,
        "created_at": dataset.created_at,
    }


@router.get("/datasets")
def list_evaluation_datasets(_: AdminUser, session: DbSession) -> list[dict]:
    rows = session.query(EvaluationDataset).order_by(EvaluationDataset.created_at.desc()).all()
    return [
        {
            "dataset_id": r.dataset_id,
            "name": r.name,
            "questions": r.questions,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/datasets/{dataset_id}/questions/{question_id}/review")
def review_evaluation_question(
    dataset_id: str,
    question_id: str,
    payload: EvaluationQuestionReviewRequest,
    session: DbSession,
    reviewer: LegalReviewerUser,
) -> dict:
    dataset = session.get(EvaluationDataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Evaluation dataset was not found.")
    questions = [dict(item) for item in dataset.questions]
    target = next((item for item in questions if item.get("question_id") == question_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Evaluation question was not found.")
    target["status"] = payload.status
    target["verified_by"] = reviewer.user_id
    dataset.questions = questions
    review = EvaluationQuestionReview(
        review_id=f"evalreview_{uuid4().hex}",
        dataset_id=dataset_id,
        question_id=question_id,
        status=payload.status,
        reviewer=reviewer.user_id,
        notes=payload.notes,
        reviewed_at=now_utc(),
    )
    session.add(review)
    session.commit()
    return {
        "dataset_id": dataset_id,
        "question_id": question_id,
        "status": payload.status,
        "verified_by": reviewer.user_id,
        "reviewed_at": review.reviewed_at,
    }


@router.post("/datasets/seed")
def load_seed_dataset(session: DbSession, _: AdminUser) -> dict:
    metadata, questions = load_evaluation_dataset(
        project_root() / "evaluation" / "golden_questions.json"
    )
    dataset_id = "evalset_golden_v1"
    dataset = EvaluationDataset(
        dataset_id=dataset_id,
        name="KerjaPedia Golden Questions v1",
        questions=[asdict(question) for question in questions],
        created_at=now_utc(),
    )
    existing = session.get(EvaluationDataset, dataset_id)
    if existing:
        existing.questions = dataset.questions
    else:
        session.add(dataset)
    session.commit()
    return {
        "dataset_id": dataset_id,
        "name": dataset.name,
        "questions": dataset.questions,
        "created_at": dataset.created_at,
        "review_status": metadata["review_status"],
    }


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
def create_evaluation_run(
    payload: EvaluationRunRequest,
    background_tasks: BackgroundTasks,
    session: DbSession,
    _: AdminUser,
) -> dict:
    dataset = session.get(EvaluationDataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset was not found.",
        )

    questions = [EvaluationQuestion.from_dict(item) for item in dataset.questions]
    if payload.release_id:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "Release-bound evaluation runs were retired with the Pinecone "
                "pipeline. Re-run without a release_id (artifact modes)."
            ),
        )
    development_count = sum(1 for question in questions if question.split == "development")
    held_out_count = sum(1 for question in questions if question.split == "test")
    progress_total = (
        (development_count + held_out_count)
        if payload.release_id
        else len(questions) * len(payload.experiment_modes)
    )
    run_id = f"evalrun_{uuid4().hex}"
    run = EvaluationRun(
        run_id=run_id,
        dataset_id=payload.dataset_id,
        release_id=payload.release_id,
        metrics={},
        report={},
        status="pending",
        progress_completed=0,
        progress_total=progress_total,
        error=None,
        created_at=now_utc(),
    )
    session.add(run)
    session.commit()
    background_tasks.add_task(
        execute_evaluation_run, run_id, list(payload.experiment_modes), payload.top_k
    )
    return {
        "run_id": run_id,
        "dataset_id": payload.dataset_id,
        "release_id": payload.release_id,
        "status": run.status,
        "progress_completed": run.progress_completed,
        "progress_total": run.progress_total,
        "error": run.error,
        "created_at": run.created_at,
        "metrics": run.metrics,
        "report": run.report,
    }


@router.get("/runs")
def list_evaluation_runs(_: AdminUser, session: DbSession) -> list[dict]:
    rows = session.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).all()
    return [
        {
            "run_id": r.run_id,
            "dataset_id": r.dataset_id,
            "release_id": r.release_id,
            "status": r.status,
            "progress_completed": r.progress_completed,
            "progress_total": r.progress_total,
            "error": r.error,
            "created_at": r.created_at,
            "metrics": r.metrics,
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
def get_evaluation_run(run_id: str, session: DbSession, _: AdminUser) -> dict:
    run = session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run was not found.",
        )
    return {
        "run_id": run.run_id,
        "dataset_id": run.dataset_id,
        "release_id": run.release_id,
        "status": run.status,
        "progress_completed": run.progress_completed,
        "progress_total": run.progress_total,
        "error": run.error,
        "created_at": run.created_at,
        "metrics": run.metrics,
        "report": run.report,
    }
