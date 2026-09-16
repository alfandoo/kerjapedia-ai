"""Offline tests for external-import job rows; no database connections."""

from datetime import UTC, datetime
from types import SimpleNamespace as NS

from app.models.ingestion import IngestionJob
from app.services.ingestion.external_postgres_import import _record_import_jobs


class FakeSession:
    def __init__(self):
        self.rows = {}

    def get(self, model, key):
        return self.rows.get((model, key))

    def add(self, row):
        self.rows[(type(row), row.job_id)] = row


def make_input():
    now = datetime.now(UTC)
    versions = {
        "PP-36-2021": NS(version_id="PP-36-2021-v3"),
        "UU-2-2004": NS(version_id="UU-2-2004-v1"),
    }
    builds = {
        "PP-36-2021": NS(build_id="extb_aaa"),
        "UU-2-2004": NS(build_id="extb_bbb"),
    }
    chunks = [
        {"document_id": "PP-36-2021"},
        {"document_id": "PP-36-2021"},
        {"document_id": "UU-2-2004"},
    ]
    staging = {"namespace": "staging-bge-m3-abc"}
    return versions, builds, chunks, staging, now


def test_records_one_completed_job_per_document():
    session = FakeSession()
    versions, builds, chunks, staging, now = make_input()
    job_ids = _record_import_jobs(session, versions, builds, chunks, staging, now)
    assert job_ids == {"PP-36-2021": "ingext_aaa", "UU-2-2004": "ingext_bbb"}
    first = session.get(IngestionJob, "ingext_aaa")
    assert first.status == "completed"
    assert first.document_id == "PP-36-2021"
    assert first.version_id == "PP-36-2021-v3"
    assert first.build_id == "extb_aaa"
    assert first.created_at == now
    assert first.artifact_paths == {
        "external_snapshot": True,
        "staging_namespace": "staging-bge-m3-abc",
        "chunk_count": 2,
    }


def test_rerun_updates_instead_of_duplicating():
    session = FakeSession()
    versions, builds, chunks, staging, first_run = make_input()
    _record_import_jobs(session, versions, builds, chunks, staging, first_run)
    second_run = datetime.now(UTC)
    job_ids = _record_import_jobs(session, versions, builds, chunks, staging, second_run)
    assert job_ids == {"PP-36-2021": "ingext_aaa", "UU-2-2004": "ingext_bbb"}
    rows = [row for (model, _), row in session.rows.items() if model is IngestionJob]
    assert len(rows) == 2
    assert session.get(IngestionJob, "ingext_aaa").created_at == second_run
