from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.routes_ingestion import _job_payload


@pytest.mark.parametrize(
    "report, stored, expected",
    [
        ({"chunks": {"count": 186}}, {}, 186),
        ({"chunks": {"count": 186}}, {"chunk_count": 0}, 186),
        ({"chunks": {"count": 0}}, {}, 0),
        ({}, {"chunk_count": 12}, 12),
        ({}, {}, None),
    ],
)
def test_chunk_count_uses_build_report_without_inventing_zero(report, stored, expected):
    job = SimpleNamespace(
        job_id="job-test", build_id="build-test", document_id="document-test",
        status="completed", created_at=datetime.now(UTC),
        artifact_paths=stored, warnings=[],
    )
    build = SimpleNamespace(quality_report=report, review_status="pending")
    result = _job_payload(job, build)["result"]
    assert result.get("chunk_count") == expected
    if expected is None:
        assert "chunk_count" not in result
