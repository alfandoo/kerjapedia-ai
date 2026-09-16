"""Background execution for evaluation runs.

Runs are admin-triggered and sequential, so FastAPI BackgroundTasks keep the
HTTP request short while the frontend polls progress. This mirrors the
ingestion non-celery fallback instead of adding a queue dependency.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from app.api.state import now_utc
from app.api.utils import storage_root
from app.core.config import settings
from app.db.session import create_session
from app.models.business import EvaluationDataset, EvaluationRun
from app.models.ingestion import RagIndexRelease
from app.services.evaluation.policy import RELEASE_QUALITY_GATES
from app.services.evaluation.ragas_metrics import build_ragas_faithfulness
from app.services.evaluation.runner import run_experiments, run_provider_evaluation
from app.services.evaluation.schemas import EvaluationQuestion
from app.services.providers import answer_generator_from_settings, pinecone_store_from_settings
from app.services.retrieval.governance import load_retrieval_governance
from app.services.retrieval.store import load_artifact_documents

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed"})
STUCK_RUN_MAX_AGE = timedelta(hours=3)


def evaluate_quality_gates(experiments: list, metrics: dict) -> tuple[dict, bool]:
    primary_mode = experiments[0]["mode"] if experiments else "rerank"
    primary_metrics = metrics.get(primary_mode, {})
    results = {}
    for gate_name, threshold in RELEASE_QUALITY_GATES.items():
        actual = primary_metrics.get(gate_name)
        results[gate_name] = {
            "threshold": threshold,
            "actual": actual,
            "passed": actual is not None and actual >= threshold,
        }
    return results, all(result["passed"] for result in results.values())


def execute_evaluation_run(run_id: str, modes: list[str], top_k: int) -> None:
    with create_session() as session:
        run = session.get(EvaluationRun, run_id)
        if run is None or run.status != "pending":
            return
        run.status = "running"
        dataset_id = run.dataset_id
        release_id = run.release_id
        session.commit()
    try:
        if release_id:
            report = _run_provider(run_id, release_id, top_k)
        else:
            report = _run_artifact(run_id, dataset_id, modes, top_k)
    except Exception as exc:
        logger.exception("evaluation run failed run_id=%s", run_id)
        with create_session() as session:
            run = session.get(EvaluationRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.error = (str(exc) or "Evaluation failed.")[:500]
            session.commit()
        return
    metrics = _metrics_by_mode(report)
    quality_gates, all_passed = evaluate_quality_gates(report["experiments"], metrics)
    report["quality_gates"] = quality_gates
    report["all_quality_gates_passed"] = all_passed
    with create_session() as session:
        run = session.get(EvaluationRun, run_id)
        if run is None:
            return
        run.metrics = metrics
        run.report = report
        run.status = "completed"
        run.progress_completed = run.progress_total
        session.commit()


def _metrics_by_mode(report: dict) -> dict:
    return {experiment["mode"]: experiment["metrics"] for experiment in report["experiments"]}


def _progress_reporter(run_id: str):
    def report(completed: int, total: int) -> None:
        try:
            with create_session() as session:
                run = session.get(EvaluationRun, run_id)
                if run is None:
                    return
                run.progress_completed = completed
                run.progress_total = total
                session.commit()
        except Exception:
            logger.warning("evaluation progress update failed run_id=%s", run_id, exc_info=True)

    return report


def _run_artifact(run_id: str, dataset_id: str, modes: list[str], top_k: int) -> dict:
    with create_session() as session:
        dataset = session.get(EvaluationDataset, dataset_id)
        if dataset is None:
            raise RuntimeError("Evaluation dataset was not found.")
        questions = [EvaluationQuestion.from_dict(item) for item in dataset.questions]
    documents = load_artifact_documents(storage_root())
    return run_experiments(questions, documents, modes, top_k, _progress_reporter(run_id))


def _run_provider(run_id: str, release_id: str, top_k: int) -> dict:
    with create_session() as session:
        release = session.get(RagIndexRelease, release_id)
        if release is None:
            raise RuntimeError("RAG index release was not found.")
        run = session.get(EvaluationRun, run_id)
        dataset_id = run.dataset_id if run else None
        dataset = session.get(EvaluationDataset, dataset_id) if dataset_id else None
        if dataset is None:
            raise RuntimeError("Evaluation dataset was not found.")
        questions = [EvaluationQuestion.from_dict(item) for item in dataset.questions]
        governance = load_retrieval_governance(session, allow_unpublished=False)
        retriever = pinecone_store_from_settings(
            settings,
            namespace=release.namespace,
            relationship_index=governance.relationship_index,
            allow_unpublished=False,
        )
        provenance = {
            "release_id": release.release_id,
            "namespace": release.namespace,
            "embedding_model": release.embedding_model,
            "reranker_model": release.reranker_model,
            "generator_model": release.generator_model,
            "verifier_model": release.verifier_model,
            "prompt_version_id": release.prompt_version_id,
            "relationship_snapshot_hash": release.relationship_snapshot_hash,
        }
    generator = answer_generator_from_settings(settings)
    report = run_provider_evaluation(
        questions=questions,
        retriever=retriever,
        generator=generator,
        top_k=top_k,
        ragas_scorer=(build_ragas_faithfulness(settings) if settings.ragas_enabled else None),
        on_progress=_progress_reporter(run_id),
    )
    report["provenance"] = provenance
    return report


def fail_stuck_runs() -> int:
    """Mark runs that can no longer be progressing (e.g. killed mid-run)."""
    cutoff = now_utc() - STUCK_RUN_MAX_AGE
    with create_session() as session:
        rows = (
            session.query(EvaluationRun)
            .filter(
                EvaluationRun.status.in_(["pending", "running"]),
                EvaluationRun.created_at < cutoff,
            )
            .all()
        )
        for run in rows:
            run.status = "failed"
            run.error = "Run terputus sebelum selesai. Silakan jalankan ulang."
        session.commit()
        return len(rows)
