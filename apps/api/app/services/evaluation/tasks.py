"""Background execution for evaluation runs.

Runs are admin-triggered and sequential, so FastAPI BackgroundTasks keep the
HTTP request short while the frontend polls progress. This mirrors the
ingestion non-celery fallback instead of adding a queue dependency.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from app.api.state import now_utc
from app.db.session import create_session
from app.models.business import EvaluationDataset, EvaluationRun
from app.services.evaluation.policy import RELEASE_QUALITY_GATES
from app.services.evaluation.runner import run_experiments
from app.services.evaluation.schemas import EvaluationQuestion

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed"})
STUCK_RUN_MAX_AGE = timedelta(hours=3)


def evaluate_quality_gates(experiments: list, metrics: dict) -> tuple[dict, bool]:
    experiment_modes = [experiment["mode"] for experiment in experiments]
    primary_mode = (
        "rerank"
        if "rerank" in experiment_modes
        else experiment_modes[0]
        if experiment_modes
        else "rerank"
    )
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
            raise RuntimeError(
                "Release-bound evaluation runs were retired with the Pinecone "
                "pipeline. Re-run without a release_id (Upstash live only)."
            )
        report = _run_upstash(run_id, dataset_id, modes, top_k)
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


def _run_upstash(run_id: str, dataset_id: str, modes: list[str], top_k: int) -> dict:
    with create_session() as session:
        dataset = session.get(EvaluationDataset, dataset_id)
        if dataset is None:
            raise RuntimeError("Evaluation dataset was not found.")
        questions = [EvaluationQuestion.from_dict(item) for item in dataset.questions]
    return run_experiments(questions, [], modes, top_k, _progress_reporter(run_id))


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
