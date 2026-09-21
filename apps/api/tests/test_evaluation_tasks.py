"""Offline tests for async evaluation runs; no database connections."""

from types import SimpleNamespace as NS

import pytest

from app.models.business import EvaluationDataset
from app.services.evaluation.policy import RELEASE_QUALITY_GATES
from app.services.evaluation.tasks import evaluate_quality_gates, execute_evaluation_run


class FakeSession:
    def __init__(self, run):
        self.run = run
        self.dataset = NS(
            dataset_id="dataset_1",
            questions=[
                {
                    "question_id": "q1",
                    "category": "pkwt",
                    "question": "Apakah pekerja PKWT memperoleh kompensasi?",
                    "expected_answer": "Ya.",
                    "expected_document_ids": ["PP-35-2021"],
                    "expected_articles": ["Pasal 15"],
                    "expected_topics": [],
                    "should_refuse": False,
                }
            ],
        )
        self.committed = 0

    def get(self, model, key):
        if model is EvaluationDataset:
            return self.dataset
        return self.run

    def commit(self):
        self.committed += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_run(**overrides):
    values = {
        "run_id": "run_async_1",
        "status": "pending",
        "dataset_id": "dataset_1",
        "release_id": None,
        "metrics": {},
        "report": {},
        "progress_completed": 0,
        "progress_total": 4,
        "error": None,
    }
    values.update(overrides)
    return NS(**values)


def fake_create_session(run):
    def factory():
        return FakeSession(run)

    return factory


def test_failed_run_is_recorded(monkeypatch):
    run = make_run()

    def boom(*args, **kwargs):
        raise RuntimeError("worker exploded")

    monkeypatch.setattr(
        "app.services.evaluation.tasks.create_session", fake_create_session(run)
    )
    monkeypatch.setattr("app.services.evaluation.tasks.run_experiments", boom)
    execute_evaluation_run("run_async_1", ["hybrid"], 5)
    assert run.status == "failed"
    assert run.error == "worker exploded"


def test_completed_run_stores_metrics_and_gates(monkeypatch):
    run = make_run()
    report = {"experiments": [{"mode": "hybrid", "metrics": {"recall_at_5": 1.0}}]}
    monkeypatch.setattr(
        "app.services.evaluation.tasks.create_session", fake_create_session(run)
    )
    monkeypatch.setattr(
        "app.services.evaluation.tasks.run_experiments", lambda *a, **k: report
    )
    execute_evaluation_run("run_async_1", ["hybrid"], 5)
    assert run.status == "completed"
    assert run.metrics == {"hybrid": {"recall_at_5": 1.0}}
    assert run.report["quality_gates"]
    assert run.progress_completed == run.progress_total == 4


def test_non_pending_run_is_left_alone(monkeypatch):
    run = make_run(status="completed")
    calls = []
    monkeypatch.setattr(
        "app.services.evaluation.tasks.create_session", fake_create_session(run)
    )
    monkeypatch.setattr(
        "app.services.evaluation.tasks.run_experiments",
        lambda *a, **k: calls.append(True),
    )
    execute_evaluation_run("run_async_1", ["hybrid"], 5)
    assert calls == []
    assert run.status == "completed"


def test_quality_gates_missing_metric_fails():
    gates, all_passed = evaluate_quality_gates([], {})
    assert not all_passed
    assert set(gates) != set()
    assert all(result["passed"] is False for result in gates.values())


def test_quality_gates_use_reranker_as_live_upstash_final_output():
    passing = {name: threshold for name, threshold in RELEASE_QUALITY_GATES.items()}
    failing = {name: 0.0 for name in RELEASE_QUALITY_GATES}

    gates, all_passed = evaluate_quality_gates(
        [{"mode": "baseline"}, {"mode": "rerank"}],
        {"baseline": failing, "rerank": passing},
    )

    assert all_passed
    assert all(result["passed"] is True for result in gates.values())


@pytest.mark.parametrize("status", ["pending", "running"])
def test_terminal_statuses(status):
    from app.services.evaluation.tasks import TERMINAL_RUN_STATUSES

    assert status not in TERMINAL_RUN_STATUSES
    assert "completed" in TERMINAL_RUN_STATUSES
    assert "failed" in TERMINAL_RUN_STATUSES
