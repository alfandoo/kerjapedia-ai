from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AdminUser, DbSession, LegalReviewerUser
from app.api.schemas import (
    EvaluationDatasetRequest,
    EvaluationQuestionReviewRequest,
    EvaluationRunRequest,
)
from app.api.state import now_utc
from app.api.utils import project_root, storage_root
from app.core.config import settings
from app.models.business import EvaluationDataset, EvaluationQuestionReview, EvaluationRun
from app.models.ingestion import DocumentRelationship, RagIndexRelease
from app.services.answering.prompts import PROMPT_VERSION_ID
from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.policy import REQUIRED_RELEASE_SCENARIOS
from app.services.evaluation.ragas_metrics import build_ragas_faithfulness
from app.services.evaluation.reviews import verified_question_reviewers
from app.services.evaluation.runner import run_experiments, run_provider_evaluation
from app.services.evaluation.schemas import EvaluationQuestion
from app.services.providers import answer_generator_from_settings, pinecone_store_from_settings
from app.services.retrieval.governance import load_retrieval_governance
from app.services.retrieval.relationships import relationship_snapshot_hash
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

    questions = [EvaluationQuestion.from_dict(item) for item in dataset.questions]
    if payload.release_id:
        release = session.get(RagIndexRelease, payload.release_id)
        if release is None:
            raise HTTPException(status_code=404, detail="RAG index release was not found.")
        if release.status != "building" or release.build_status != "succeeded":
            raise HTTPException(
                status_code=409,
                detail="The RAG index release must finish building before evaluation.",
            )
        if len(questions) < 300 or {question.split for question in questions} != {
            "development",
            "test",
        }:
            raise HTTPException(
                status_code=409,
                detail="Release evaluation requires at least 300 questions and both splits.",
            )
        if len({question.question_id for question in questions}) != len(questions) or len(
            {" ".join(question.question.lower().split()) for question in questions}
        ) != len(questions):
            raise HTTPException(
                status_code=409,
                detail="Release evaluation requires unique question IDs and texts.",
            )
        covered_scenarios = {tag for question in questions for tag in question.scenario_tags}
        missing_scenarios = sorted(REQUIRED_RELEASE_SCENARIOS - covered_scenarios)
        if missing_scenarios:
            raise HTTPException(
                status_code=409,
                detail={"missing_release_scenarios": missing_scenarios},
            )
        if any(
            question.status != "verified" or question.verified_by in {"", "unknown"}
            for question in questions
        ):
            raise HTTPException(
                status_code=409,
                detail="Release evaluation requires a fully human-verified dataset.",
            )
        if {
            "embedding": release.embedding_model,
            "reranker": release.reranker_model,
            "generator": release.generator_model,
            "verifier": release.verifier_model,
            "prompt": release.prompt_version_id,
        } != {
            "embedding": settings.embedding_model,
            "reranker": settings.reranker_model,
            "generator": settings.groq_model,
            "verifier": settings.claim_verifier_model,
            "prompt": PROMPT_VERSION_ID,
        }:
            raise HTTPException(
                status_code=409,
                detail="Release model provenance does not match the evaluation runtime.",
            )
        if release.relationship_snapshot_hash != relationship_snapshot_hash(
            session.query(DocumentRelationship).all()
        ):
            raise HTTPException(
                status_code=409,
                detail="Release legal-relationship snapshot is stale.",
            )
        verified_reviewers = verified_question_reviewers(session, dataset.dataset_id)
        if set(verified_reviewers) != {question.question_id for question in questions} or any(
            verified_reviewers.get(question.question_id) != question.verified_by
            for question in questions
        ):
            raise HTTPException(
                status_code=409,
                detail="Release evaluation requires an audit record for every legal review.",
            )
        if not (
            settings.vector_store == "pinecone"
            and settings.embedding_provider == "bge_m3"
            and settings.llm_provider == "groq"
            and settings.reranker_provider == "pinecone"
            and settings.claim_verifier_provider == "groq"
            and settings.rag_fail_closed
        ):
            raise HTTPException(
                status_code=409,
                detail="Release evaluation requires the fail-closed production RAG providers.",
            )
        governance = load_retrieval_governance(session, allow_unpublished=False)
        report = run_provider_evaluation(
            questions=questions,
            retriever=pinecone_store_from_settings(
                settings,
                namespace=release.namespace,
                relationship_index=governance.relationship_index,
                allow_unpublished=False,
            ),
            generator=answer_generator_from_settings(settings),
            top_k=payload.top_k,
            ragas_scorer=(build_ragas_faithfulness(settings) if settings.ragas_enabled else None),
        )
        report["provenance"] = {
            "release_id": release.release_id,
            "namespace": release.namespace,
            "embedding_model": release.embedding_model,
            "reranker_model": release.reranker_model,
            "generator_model": release.generator_model,
            "verifier_model": release.verifier_model,
            "prompt_version_id": release.prompt_version_id,
            "relationship_snapshot_hash": release.relationship_snapshot_hash,
        }
    else:
        documents = load_artifact_documents(storage_root())
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
        release_id=payload.release_id,
        metrics={experiment["mode"]: experiment["metrics"] for experiment in report["experiments"]},
        report=report,
        created_at=now_utc(),
    )
    session.add(run)
    session.commit()
    return {
        "run_id": run_id,
        "dataset_id": payload.dataset_id,
        "release_id": payload.release_id,
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
            "release_id": r.release_id,
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
        "created_at": run.created_at,
        "metrics": run.metrics,
        "report": run.report,
    }
