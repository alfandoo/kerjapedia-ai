"""Offline access regression tests; run with --noconftest."""

import socket
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dependencies as deps
from app.api import routes_documents as routes
from app.services.ingestion.schemas import DocumentMetadata


@pytest.fixture
def env(monkeypatch, tmp_path):
    original_connect = socket.socket.connect

    def offline_connect(sock, address):
        # Windows asyncio creates its internal socketpair over loopback.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        raise AssertionError("External network forbidden")

    monkeypatch.setattr(socket.socket, "connect", offline_connect)
    data = b"%PDF-1.4 test"
    path = tmp_path / "dataset" / "test.pdf"
    path.parent.mkdir()
    path.write_bytes(data)
    doc = DocumentMetadata(
        "test",
        "Test",
        "Test",
        "PP",
        1,
        2025,
        "issuer",
        [],
        "active",
        "source",
        "https://peraturan.bpk.go.id/Details/1/test",
        "dataset/test.pdf",
        "test.pdf",
        len(data),
        sha256(data).hexdigest(),
        "verified",
        "verified",
        "verified",
    )
    access = SimpleNamespace(eligible_versions={"test": 1}, eligible_builds={"test-v1": "approved"})
    row = SimpleNamespace(
        sha256=doc.sha256,
        local_file=doc.local_file,
        source_url=doc.source_url,
        legal_status="active",
    )
    session = Mock()
    session.get.return_value = row
    monkeypatch.setattr(routes, "merged_documents", lambda: [doc])
    monkeypatch.setattr(routes, "project_root", lambda: tmp_path)
    monkeypatch.setattr(routes, "storage_root", lambda: tmp_path)
    governance = Mock(return_value=access)
    monkeypatch.setattr(routes, "load_retrieval_governance", governance)
    chunks = Mock(return_value=[])
    monkeypatch.setattr(routes, "load_artifact_documents", chunks)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[deps.get_db] = lambda: session
    app.dependency_overrides[deps.get_optional_user] = lambda: None
    return SimpleNamespace(
        client=TestClient(app),
        app=app,
        access=access,
        row=row,
        doc=doc,
        path=path,
        chunks=chunks,
        governance=governance,
    )


@pytest.mark.parametrize("suffix", ["", "/pdf", "/citations/secret"])
def test_draft_direct_access_is_not_found(env, suffix):
    env.access.eligible_versions = {}
    assert env.client.get("/documents/test" + suffix).status_code == 404
    env.chunks.assert_not_called()


def test_public_list_hides_drafts_and_replacement_uploads(env):
    assert len(env.client.get("/documents").json()) == 1
    env.row.sha256 = "unreviewed replacement"
    assert env.client.get("/documents").json() == []
    env.access.eligible_versions = {}
    assert env.client.get("/documents").json() == []


def test_published_detail_and_pdf_are_available_without_local_paths(env):
    response = env.client.get("/documents/test")
    assert response.status_code == 200
    assert "local_file" not in response.json()
    assert response.headers["cache-control"] == "private, no-store"
    assert env.client.get("/documents/test/pdf").status_code == 200
    env.governance.assert_called_with(
        env.app.dependency_overrides[deps.get_db](), allow_unpublished=False
    )
    assert env.chunks.call_args.kwargs == {
        "eligible_versions": {"test": 1},
        "eligible_builds": {"test-v1": "approved"},
    }


def test_changed_pdf_is_not_served(env):
    env.path.write_bytes(b"unapproved content")
    assert env.client.get("/documents/test/pdf").status_code == 404


def test_missing_approved_build_never_falls_back_to_latest(env):
    env.access.eligible_builds = {}
    assert env.client.get("/documents/test/citations/new").status_code == 404
    assert env.chunks.call_args.kwargs["eligible_versions"] == {}


@pytest.mark.parametrize(
    "roles,expected", [(["user"], 404), (["legal_reviewer"], 404), (["admin"], 200)]
)
def test_only_verified_admin_can_preview_draft(env, roles, expected):
    env.access.eligible_versions = {}
    env.app.dependency_overrides[deps.get_optional_user] = lambda: SimpleNamespace(roles=roles)
    assert env.client.get("/documents/test").status_code == expected


def test_invalid_bearer_is_rejected(env, monkeypatch):
    del env.app.dependency_overrides[deps.get_optional_user]
    monkeypatch.setattr(deps, "_get_user_from_supabase", lambda token: None)
    assert (
        env.client.get("/documents/test", headers={"Authorization": "Bearer fake"}).status_code
        == 401
    )


def test_citations_use_only_published_version_and_approved_build(env, monkeypatch, tmp_path):
    import json

    from app.services.retrieval.store import load_artifact_documents

    for version, build, chunk_id in [
        (1, "approved", "public"),
        (1, "draft", "secret-build"),
        (2, "new", "secret-version"),
    ]:
        folder = tmp_path / "documents" / "test" / f"v{version}" / "builds" / build / "processed"
        folder.mkdir(parents=True)
        (folder / "chunks.json").write_text(
            json.dumps(
                [
                    {
                        "chunk_id": chunk_id,
                        "document_id": "test",
                        "text": chunk_id,
                        "page_start": 1,
                        "page_end": 1,
                        "token_count": 1,
                    }
                ]
            )
        )
    monkeypatch.setattr(routes, "load_artifact_documents", load_artifact_documents)
    assert env.client.get("/documents/test/citations/public").json()["quote"] == "public"
    for chunk_id in ("secret-build", "secret-version"):
        assert env.client.get(f"/documents/test/citations/{chunk_id}").status_code == 404
    assert env.client.get("/documents/test").json()["chunk_count"] == 1
