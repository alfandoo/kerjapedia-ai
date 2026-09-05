"""Exercise actual ASGI request streaming with tiny limits and mocked writes."""

import asyncio
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request
from starlette.requests import ClientDisconnect

from app.api import routes_admin as routes


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(routes, "MAX_UPLOAD_BYTES", 16)
    storage = Mock(return_value="https://offline.invalid/pdf")
    manifest = Mock(return_value=NS(sha256="hash"))
    audit = Mock()
    monkeypatch.setattr(routes, "upload_bytes", storage)
    monkeypatch.setattr(routes, "register_upload", manifest)
    monkeypatch.setattr(routes, "log_audit", audit)
    return NS(storage=storage, manifest=manifest, audit=audit, session=Mock())


def request(chunks, length=None, disconnect=False):
    count = [0]

    async def receive():
        i = count[0]
        count[0] += 1
        if i == len(chunks) and disconnect:
            return {"type": "http.disconnect"}
        assert i < len(chunks), "Reader consumed beyond the test stream"
        return {
            "type": "http.request",
            "body": chunks[i],
            "more_body": i < len(chunks) - 1 or disconnect,
        }

    headers = [] if length is None else [(b"content-length", length.encode())]
    return Request({"type": "http", "headers": headers}, receive), count


def upload(env, req):
    return asyncio.run(
        routes.upload_document(req, env.session, NS(user_id="admin"), "valid.pdf", "topic")
    )


def assert_no_writes(env):
    env.storage.assert_not_called()
    env.manifest.assert_not_called()
    env.audit.assert_not_called()
    env.session.add.assert_not_called()
    env.session.commit.assert_not_called()


@pytest.mark.parametrize("length", ["17", "9" * 100])
def test_declared_oversize_is_rejected_before_reading(env, length):
    req, reads = request([b"%PDF-"], length)
    with pytest.raises(HTTPException) as exc:
        upload(env, req)
    assert exc.value.status_code == 413
    assert reads[0] == 0
    assert_no_writes(env)


@pytest.mark.parametrize("length", [None, "5", "16"])
def test_actual_oversize_stops_stream_even_if_header_missing_or_false(env, length):
    req, reads = request([b"%PDF-", b"x" * 12, b"must not read"], length)
    with pytest.raises(HTTPException) as exc:
        upload(env, req)
    assert exc.value.status_code == 413
    assert reads[0] == 2
    assert_no_writes(env)


@pytest.mark.parametrize("length", [None, "16"])
def test_exact_limit_pdf_is_accepted_and_preserved(env, length):
    req, _ = request([b"%P", b"DF-", b"x" * 11], length)
    result = upload(env, req)
    assert result["size_bytes"] == 16
    assert env.storage.call_args.args[0] == b"%PDF-" + b"x" * 11
    env.session.commit.assert_called_once()


@pytest.mark.parametrize("length", ["-1", "abc", "1,2", "+5", ""])
def test_malformed_length_rejected_without_reading(env, length):
    req, reads = request([b"%PDF-"], length)
    with pytest.raises(HTTPException) as exc:
        upload(env, req)
    assert exc.value.status_code == 400
    assert reads[0] == 0
    assert_no_writes(env)


def test_truncated_body_is_not_stored(env):
    req, _ = request([b"%PDF-"], "10")
    with pytest.raises(HTTPException) as exc:
        upload(env, req)
    assert exc.value.status_code == 400
    assert_no_writes(env)


@pytest.mark.parametrize("body", [b"", b"not a PDF"])
def test_empty_or_non_pdf_body_rejected(env, body):
    req, _ = request([body])
    with pytest.raises(HTTPException) as exc:
        upload(env, req)
    assert exc.value.status_code == 400
    assert_no_writes(env)


def test_disconnect_does_not_persist_partial_upload(env):
    req, _ = request([b"%PDF-"], disconnect=True)
    with pytest.raises(ClientDisconnect):
        upload(env, req)
    assert_no_writes(env)
