"""Offline proxy spoofing regression tests (no application lifespan)."""

import asyncio
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import server
from app.main import rate_limit_and_log, settings, state


@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "::/0", "127.0.0.1,*", "not-an-ip"])
def test_rejects_unsafe_proxy_trust(value):
    with pytest.raises(ValueError):
        server.trusted_proxy_ips(value)


def test_container_defaults_to_no_proxy_headers(monkeypatch):
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    run = Mock()
    monkeypatch.setattr(server.uvicorn, "run", run)
    server.main()
    assert run.call_args.kwargs["proxy_headers"] is False
    assert run.call_args.kwargs["forwarded_allow_ips"] == []


def test_container_uses_explicit_proxy_addresses(monkeypatch):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.30.0.10, 2001:db8::1")
    run = Mock()
    monkeypatch.setattr(server.uvicorn, "run", run)
    server.main()
    assert run.call_args.kwargs["forwarded_allow_ips"] == ["172.30.0.10", "2001:db8::1"]
    assert run.call_args.kwargs["proxy_headers"] is True


@pytest.mark.parametrize(
    "trusted,peer,headers",
    [
        ([], "198.51.100.20", ["1.1.1.1", "2.2.2.2", "3.3.3.3"]),
        (["172.30.0.10"], "198.51.100.20", ["1.1.1.1", "2.2.2.2", "3.3.3.3"]),
        (
            ["172.30.0.10"],
            "172.30.0.10",
            ["1.1.1.1, 198.51.100.20", "2.2.2.2, 198.51.100.20", "3.3.3.3, 198.51.100.20"],
        ),
    ],
)
def test_rotating_spoofed_headers_cannot_reset_rate_limit(monkeypatch, trusted, peer, headers):
    monkeypatch.setattr(state, "request_counts", {})
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    statuses = []

    async def downstream(request):
        return JSONResponse({"ok": True})

    async def application(scope, receive, send):
        response = await rate_limit_and_log(Request(scope), downstream)
        statuses.append(response.status_code)

    proxy = ProxyHeadersMiddleware(application, trusted_hosts=trusted)

    async def exercise():
        for header in headers:
            scope = {
                "type": "http",
                "method": "GET",
                "scheme": "http",
                "path": "/test",
                "query_string": b"",
                "server": ("localhost", 8000),
                "client": (peer, 1234),
                "headers": [
                    (b"x-forwarded-for", header.encode()),
                    (b"x-real-ip", header.encode()),
                    (b"forwarded", b"for=8.8.8.8"),
                ],
            }
            await proxy(scope, None, None)

    asyncio.run(exercise())
    assert statuses == [200, 200, 429]
    assert list(state.request_counts) == ["198.51.100.20"]


def test_trusted_proxy_preserves_distinct_client_ips(monkeypatch):
    clients = []

    async def application(scope, receive, send):
        clients.append(scope["client"][0])

    proxy = ProxyHeadersMiddleware(
        application, trusted_hosts=server.trusted_proxy_ips("172.30.0.10")
    )

    async def exercise():
        for ip in ("198.51.100.1", "198.51.100.2"):
            await proxy(
                {
                    "type": "http",
                    "client": ("172.30.0.10", 1234),
                    "headers": [(b"x-forwarded-for", ip.encode())],
                },
                None,
                None,
            )

    asyncio.run(exercise())
    assert clients == ["198.51.100.1", "198.51.100.2"]
