from fastapi import HTTPException

from app.api import routes_auth


class _Client:
    host = "1.2.3.4"


class _Request:
    def __init__(self) -> None:
        self.headers = {}
        self.client = _Client()


def test_login_methods_rejects_malformed_email() -> None:
    try:
        routes_auth.login_methods(request=_Request(), email="not-an-email")  # type: ignore[arg-type]
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("malformed email must be rejected")


def test_login_methods_rate_limited_after_budget() -> None:
    assert routes_auth._login_methods_limiter is not None
    routes_auth._login_methods_limiter._limit = 1
    req = _Request()
    first = routes_auth.login_methods(request=req, email="someone@example.com")  # type: ignore[arg-type]
    assert first.email_exists in (True, False)
    try:
        routes_auth.login_methods(request=req, email="someone@example.com")  # type: ignore[arg-type]
    except HTTPException as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("second call must be rate limited")
