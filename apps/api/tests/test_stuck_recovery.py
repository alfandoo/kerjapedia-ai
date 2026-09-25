"""Offline tests for stuck-job recovery; no database connections."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

import pytest

from app.models.ingestion import DocumentVersion, IngestionBuild, IngestionJob
from app.services.ingestion import recovery as ingestion_recovery


def _old() -> datetime:
    return datetime.now(UTC) - timedelta(hours=5)


def _fresh() -> datetime:
    return datetime.now(UTC)


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Routes queries by model; caller pre-filters rows by age like SQL would."""

    def __init__(self, jobs, builds, versions, healthy_build=None):
        self._jobs = jobs
        self._builds = builds
        self._versions = {v.version_id: v for v in versions}
        self._healthy_build = healthy_build
        self.committed = 0

    def query(self, *models):
        first = models[0] if models else None
        if first is IngestionJob:
            return FakeQuery(self._jobs)
        # Single-column health check (IngestionBuild.build_id) or full build query.
        if self._healthy_build is not None and first is not IngestionBuild:
            return FakeQuery([self._healthy_build])
        return FakeQuery(self._builds if first is IngestionBuild else [])

    def get(self, model, key):
        if model is DocumentVersion:
            return self._versions.get(key)
        return None

    def commit(self):
        self.committed += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _job(status, created_at):
    return NS(status=status, created_at=created_at, warnings=[])


def _build(status, created_at, version_id="v1"):
    return NS(status=status, created_at=created_at, version_id=version_id, quality_report={})


def _version(version_id="v1", ingestion_status="running"):
    return NS(version_id=version_id, ingestion_status=ingestion_status)


def test_stuck_jobs_and_builds_recovered(monkeypatch):
    jobs = [_job("running", _old())]
    builds = [_build("queued", _old())]
    versions = [_version()]
    session = FakeSession(jobs, builds, versions)
    monkeypatch.setattr("app.services.ingestion.recovery.create_session", lambda: session)
    counts = ingestion_recovery.recover_stuck_ingestion_jobs(max_age=timedelta(hours=2))
    assert counts["jobs"] == 1
    assert counts["builds"] == 1
    assert counts["versions"] == 1
    assert jobs[0].status == "failed"
    assert "stuck_recovered:worker_lost" in jobs[0].warnings
    assert builds[0].status == "failed"
    assert versions[0].ingestion_status == "failed"
    assert session.committed == 1


def test_terminal_states_never_touched(monkeypatch):
    session = FakeSession([], [], [_version(ingestion_status="completed")])
    monkeypatch.setattr("app.services.ingestion.recovery.create_session", lambda: session)
    counts = ingestion_recovery.recover_stuck_ingestion_jobs(max_age=timedelta(hours=2))
    assert counts == {"jobs": 0, "builds": 0, "versions": 0}


def test_version_with_healthy_build_not_downgraded(monkeypatch):
    builds = [_build("queued", _old(), version_id="v9")]
    versions = [_version(version_id="v9", ingestion_status="running")]
    session = FakeSession([], builds, versions, healthy_build=NS(build_id="good"))
    monkeypatch.setattr("app.services.ingestion.recovery.create_session", lambda: session)
    counts = ingestion_recovery.recover_stuck_ingestion_jobs(max_age=timedelta(hours=2))
    assert counts["builds"] == 1
    assert counts["versions"] == 0
    assert versions[0].ingestion_status == "running"


def test_beat_schedule_covers_recovery():
    pytest.importorskip("celery")
    from app.services.ingestion import tasks as ingestion_tasks

    schedule = ingestion_tasks.celery_app.conf.beat_schedule
    assert (
        schedule["recover-stuck-ingestion-hourly"]["task"]
        == "kerjapedia.ingestion.recover_stuck"
    )
    assert (
        schedule["fail-stuck-evaluations-hourly"]["task"]
        == "kerjapedia.evaluation.fail_stuck"
    )
    assert "purge-expired-rag-traces-daily" in schedule
