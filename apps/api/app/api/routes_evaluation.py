from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AdminUser, DbSession
from app.api.schemas import EvaluationDatasetRequest, EvaluationRunRequest
from app.api.state import now_utc
from app.api.utils import project_root, storage_root
from app.models.business import EvaluationDataset, EvaluationRun
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.runner import run_experiments
from app.services.evaluation.schemas import EvaluationQuestion
from app.services.retrieval.store import load_artifact_documents

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
        questions=[question.model_dump() for question in payload.questions],
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


@router.post("/runs")
def create_evaluation_run(
    payload: EvaluationRunRequest,
    session: DbSession,
    _: AdminUser,
) -> dict:
    dataset = session.get(EvaluationDataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset was not found.",
        )

    documents = load_artifact_documents(storage_root())
    questions = [EvaluationQuestion.from_dict(item) for item in dataset.questions]
    report = run_experiments(
        questions=questions,
        documents=documents,
        modes=payload.experiment_modes,
        top_k=payload.top_k,
    )

    run_id = f"evalrun_{uuid4().hex}"
    run = EvaluationRun(
        run_id=run_id,
        dataset_id=payload.dataset_id,
        metrics={
            experiment["mode"]: experiment["metrics"] for experiment in report["experiments"]
        },
        report=report,
        created_at=now_utc(),
    )
    session.add(run)
    session.commit()
    return {
        "run_id": run_id,
        "dataset_id": payload.dataset_id,
        "created_at": run.created_at,
        "metrics": run.metrics,
        "report": report,
    }


@router.get("/runs")
def list_evaluation_runs(_: AdminUser, session: DbSession) -> list[dict]:
    rows = session.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).all()
    return [
        {
            "run_id": r.run_id,
            "dataset_id": r.dataset_id,
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
        "created_at": run.created_at,
        "metrics": run.metrics,
        "report": run.report,
    }
