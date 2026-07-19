from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AdminUser
from app.api.schemas import EvaluationDatasetRequest, EvaluationRunRequest
from app.api.state import now_utc, state
from app.api.utils import project_root, storage_root
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.runner import run_experiments
from app.services.evaluation.schemas import EvaluationQuestion
from app.services.retrieval.store import load_artifact_documents

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/datasets")
def create_evaluation_dataset(
    payload: EvaluationDatasetRequest,
    _: AdminUser,
) -> dict:
    dataset_id = f"evalset_{uuid4().hex}"
    dataset = {
        "dataset_id": dataset_id,
        "name": payload.name,
        "questions": [question.model_dump() for question in payload.questions],
        "created_at": now_utc(),
    }
    state.evaluation_datasets[dataset_id] = dataset
    return dataset


@router.get("/datasets")
def list_evaluation_datasets(_: AdminUser) -> list[dict]:
    return list(state.evaluation_datasets.values())


@router.post("/datasets/seed")
def load_seed_dataset(_: AdminUser) -> dict:
    metadata, questions = load_evaluation_dataset(
        project_root() / "evaluation" / "golden_questions.json"
    )
    dataset_id = "evalset_golden_v1"
    dataset = {
        "dataset_id": dataset_id,
        "name": "KerjaPedia Golden Questions v1",
        "questions": [asdict(question) for question in questions],
        "created_at": now_utc(),
        "review_status": metadata["review_status"],
    }
    state.evaluation_datasets[dataset_id] = dataset
    return dataset


@router.post("/runs")
def create_evaluation_run(
    payload: EvaluationRunRequest,
    _: AdminUser,
) -> dict:
    dataset = state.evaluation_datasets.get(payload.dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset was not found.",
        )

    documents = load_artifact_documents(storage_root())
    questions = [EvaluationQuestion.from_dict(item) for item in dataset["questions"]]
    report = run_experiments(
        questions=questions,
        documents=documents,
        modes=payload.experiment_modes,
        top_k=payload.top_k,
    )

    run_id = f"evalrun_{uuid4().hex}"
    run = {
        "run_id": run_id,
        "dataset_id": payload.dataset_id,
        "created_at": now_utc(),
        "metrics": {
            experiment["mode"]: experiment["metrics"] for experiment in report["experiments"]
        },
        "report": report,
    }
    state.evaluation_runs[run_id] = run
    return run


@router.get("/runs")
def list_evaluation_runs(_: AdminUser) -> list[dict]:
    return list(state.evaluation_runs.values())


@router.get("/runs/{run_id}")
def get_evaluation_run(run_id: str, _: AdminUser) -> dict:
    run = state.evaluation_runs.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run was not found.",
        )
    return run
