import json
from collections.abc import Iterator
from statistics import median

import pytest
from fastapi.testclient import TestClient

from app.api.state import state
from app.main import app
from app.services.ingestion.embeddings import HashEmbeddingProvider
from app.services.retrieval.schemas import RetrievalDocument


@pytest.fixture(autouse=True)
def reset_api_state() -> Iterator[None]:
    with state.lock:
        state.sessions.clear()
        state.conversations.clear()
        state.feedback.clear()
        state.ingestion_jobs.clear()
        state.document_admin.clear()
        state.uploaded_documents.clear()
        state.evaluation_datasets.clear()
        state.evaluation_runs.clear()
        state.request_counts.clear()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def make_document() -> RetrievalDocument:
    provider = HashEmbeddingProvider()
    text = "Pasal 15 pekerja PKWT berhak memperoleh uang kompensasi."
    return RetrievalDocument(
        chunk_id="chunk-1",
        document_id="PP-35-2021",
        text=text,
        chapter="BAB II",
        section="Perjanjian Kerja Waktu Tertentu",
        article="Pasal 15",
        paragraph="Ayat (1)",
        page_start=12,
        page_end=12,
        token_count=len(text.split()),
        topics=["pkwt"],
        legal_status="active",
        source_url="https://peraturan.bpk.go.id/",
        embedding_model=provider.model_name,
        embedding=provider.embed([text])[0],
        metadata={
            "title": "Peraturan Pemerintah Nomor 35 Tahun 2021",
            "short_title": "PP 35/2021",
            "local_file": "dataset/PP-35-2021.pdf",
            "year": 2021,
            "regulation_type": "PP",
        },
    )


def admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "secret"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_auth_login_and_current_user(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "secret"},
    )

    assert login.status_code == 200
    token = login.json()["access_token"]
    current = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert current.status_code == 200
    assert current.json()["roles"] == ["user", "admin"]


def test_auth_rejects_wrong_admin_password(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "wrong"},
    )

    assert response.status_code == 401


def test_auth_does_not_promote_admin_prefix(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "admin@attacker.example", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["roles"] == ["user"]


def test_security_and_trace_headers_are_added(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["X-Request-ID"] == "test-request-id"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_chat_ask_returns_structured_answer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes_chat.load_artifact_documents",
        lambda _: [make_document()],
    )

    response = client.post(
        "/chat/ask",
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"].startswith("conv_")
    assert payload["answer"]["citations"][0]["article"] == "Pasal 15"
    assert payload["retrieval_score"] is not None


def test_guest_conversations_are_isolated_by_guest_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes_chat.load_artifact_documents",
        lambda _: [make_document()],
    )
    first_guest = {"X-KerjaPedia-Guest-ID": "11111111-1111-4111-8111-111111111111"}
    second_guest = {"X-KerjaPedia-Guest-ID": "22222222-2222-4222-8222-222222222222"}

    created = client.post(
        "/chat/ask",
        headers=first_guest,
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
    )
    conversation_id = created.json()["conversation_id"]

    own_history = client.get("/chat/conversations", headers=first_guest)
    other_history = client.get("/chat/conversations", headers=second_guest)
    forbidden = client.get(
        f"/chat/conversations/{conversation_id}",
        headers=second_guest,
    )

    assert own_history.status_code == 200
    assert own_history.json() == []
    assert other_history.json() == []
    assert forbidden.status_code == 403


def test_authenticated_user_conversation_is_saved_to_history(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes_chat.load_artifact_documents",
        lambda _: [make_document()],
    )
    login = client.post(
        "/auth/login",
        json={"email": "pekerja@example.com", "password": "secret"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    created = client.post(
        "/chat/ask",
        headers=headers,
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
    )
    history = client.get("/chat/conversations", headers=headers)

    assert created.status_code == 200
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["conversation_id"] == created.json()["conversation_id"]


def test_guest_id_must_be_uuid(client: TestClient) -> None:
    response = client.get(
        "/chat/conversations",
        headers={"X-KerjaPedia-Guest-ID": "not-a-uuid"},
    )

    assert response.status_code == 400


def test_guest_can_rename_and_delete_own_conversation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes_chat.load_artifact_documents",
        lambda _: [make_document()],
    )
    owner = {"X-KerjaPedia-Guest-ID": "11111111-1111-4111-8111-111111111111"}
    other_guest = {"X-KerjaPedia-Guest-ID": "22222222-2222-4222-8222-222222222222"}
    created = client.post(
        "/chat/ask",
        headers=owner,
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
    )
    conversation_id = created.json()["conversation_id"]

    forbidden_rename = client.patch(
        f"/chat/conversations/{conversation_id}",
        headers=other_guest,
        json={"title": "Percakapan orang lain"},
    )
    renamed = client.patch(
        f"/chat/conversations/{conversation_id}",
        headers=owner,
        json={"title": "  Hak kompensasi PKWT  "},
    )
    forbidden_delete = client.delete(
        f"/chat/conversations/{conversation_id}",
        headers=other_guest,
    )
    deleted = client.delete(
        f"/chat/conversations/{conversation_id}",
        headers=owner,
    )
    missing = client.get(f"/chat/conversations/{conversation_id}", headers=owner)

    assert forbidden_rename.status_code == 403
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Hak kompensasi PKWT"
    assert forbidden_delete.status_code == 403
    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_chat_stream_emits_thinking_deltas_and_final_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes_chat.load_artifact_documents",
        lambda _: [make_document()],
    )

    with client.stream(
        "POST",
        "/chat/ask/stream",
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert events[0]["event"] == "start"
    assert [event["status"] for event in events if event["event"] == "thinking"] == [
        "Menelusuri regulasi resmi",
        "Menyusun jawaban berdasarkan sumber",
    ]
    streamed_answer = "".join(
        event["content"] for event in events if event["event"] == "delta"
    )
    completed = next(event["response"] for event in events if event["event"] == "done")
    assert streamed_answer == completed["answer"]["answer"]
    assert completed["conversation_id"].startswith("conv_")


def test_chat_refuses_when_no_document_supports_the_question(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.routes_chat.load_artifact_documents", lambda _: [])

    response = client.post(
        "/chat/ask",
        json={"question": "Berapa harga saham perusahaan hari ini?", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]["refusal_reason"] == "no_retrieved_chunk_passed_minimum_score"
    assert payload["answer"]["citations"] == []
    assert payload["retrieval_score"] is None


def test_chat_median_response_time_meets_prd_target(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes_chat.load_artifact_documents",
        lambda _: [make_document()],
    )

    responses = [
        client.post(
            "/chat/ask",
            json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 1},
        )
        for _ in range(9)
    ]
    latencies = [response.json()["latency_ms"] for response in responses]

    assert all(response.status_code == 200 for response in responses)
    assert median(latencies) <= 5_000
    assert all("X-Request-Latency-Ms" in response.headers for response in responses)


def test_documents_and_openapi_are_available(client: TestClient) -> None:
    documents = client.get("/documents")
    openapi = client.get("/openapi.json")

    assert documents.status_code == 200
    assert len(documents.json()) > 0
    assert openapi.status_code == 200
    assert "/chat/ask" in openapi.json()["paths"]


def test_admin_document_workflow_requires_admin(client: TestClient) -> None:
    unauthorized = client.get("/admin/documents")
    headers = admin_headers(client)
    documents = client.get("/admin/documents", headers=headers)

    assert unauthorized.status_code == 401
    assert documents.status_code == 200
    assert documents.json()["summary"]["documents"] > 0

    update = client.patch(
        "/admin/documents/PP-35-2021",
        headers=headers,
        json={"legal_status": "active", "verification_status": "verified"},
    )
    relationship = client.put(
        "/admin/documents/PP-35-2021/relationships",
        headers=headers,
        json=[
            {
                "to_document_id": "UU-6-2023",
                "relationship_type": "amended_by",
                "confidence": "high",
            }
        ],
    )
    publication = client.post(
        "/admin/documents/PP-35-2021/publication",
        headers=headers,
        json={"action": "publish"},
    )

    assert update.status_code == 200
    assert relationship.status_code == 200
    assert relationship.json()["relationships"][0]["to_document_id"] == "UU-6-2023"
    assert publication.status_code == 200
    assert publication.json()["status"] == "published"


def test_admin_upload_validates_and_stores_pdf(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    headers = admin_headers(client)
    monkeypatch.setattr("app.api.routes_admin.project_root", lambda: tmp_path)

    invalid = client.post(
        "/admin/documents/upload?file_name=invalid.pdf&topic=pkwt",
        headers={**headers, "Content-Type": "application/pdf"},
        content=b"not-pdf",
    )
    uploaded = client.post(
        "/admin/documents/upload?file_name=PP-99-2026.pdf&topic=pkwt",
        headers={**headers, "Content-Type": "application/pdf"},
        content=b"%PDF-1.7\nadmin-test",
    )

    assert invalid.status_code == 400
    assert uploaded.status_code == 201
    assert uploaded.json()["document_id"] == "PP-99-2026"
    assert list((tmp_path / "storage" / "uploads").glob("*.pdf"))


def test_admin_retrieval_playground_returns_ranked_chunks(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = admin_headers(client)
    monkeypatch.setattr(
        "app.api.routes_admin.load_artifact_documents",
        lambda _: [make_document()],
    )

    response = client.post(
        "/admin/retrieval/search",
        headers=headers,
        json={"question": "Apakah pekerja PKWT memperoleh kompensasi?", "top_k": 5},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["article"] == "Pasal 15"


def test_feedback_listing_is_admin_only(client: TestClient) -> None:
    created = client.post(
        "/feedback",
        json={"question": "Apakah jawaban ini benar?", "rating": "helpful"},
    )
    unauthorized = client.get("/feedback")
    authorized = client.get("/feedback", headers=admin_headers(client))

    assert created.status_code == 200
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()[0]["rating"] == "helpful"


def test_evaluation_dataset_and_experiment_run(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = admin_headers(client)
    dataset = client.post(
        "/evaluation/datasets",
        headers=headers,
        json={
            "name": "API regression",
            "questions": [
                {
                    "question_id": "API-EVAL-001",
                    "category": "pkwt",
                    "question": "Apakah pekerja PKWT memperoleh kompensasi?",
                    "expected_answer": "Pekerja PKWT memperoleh kompensasi.",
                    "expected_document_ids": ["PP-35-2021"],
                    "expected_articles": ["Pasal 15"],
                    "expected_topics": ["pkwt"],
                    "should_refuse": False,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "app.api.routes_evaluation.load_artifact_documents",
        lambda _: [make_document()],
    )
    run = client.post(
        "/evaluation/runs",
        headers=headers,
        json={
            "dataset_id": dataset.json()["dataset_id"],
            "top_k": 5,
            "experiment_modes": ["baseline", "dense", "hybrid", "rerank"],
        },
    )

    assert dataset.status_code == 200
    assert run.status_code == 200
    assert set(run.json()["metrics"]) == {"baseline", "dense", "hybrid", "rerank"}
    assert run.json()["metrics"]["rerank"]["recall_at_5"] == 1.0
