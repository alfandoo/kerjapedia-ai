from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.state import UserRecord
from app.db.session import create_session
from app.models.business import UserProfile
from app.services import supabase as supabase_service


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _token_is_expired(token: str) -> bool:
    try:
        import base64
        import json
        import time

        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
        expires_at = payload.get("exp")
        if expires_at is None:
            return False
        return time.time() >= float(expires_at)
    except Exception:
        return False


def _get_user_from_supabase(token: str) -> UserRecord | None:
    if _token_is_expired(token):
        return None
    try:
        supabase = supabase_service.get_supabase()
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            return None
        uid = user.user.id
        email = user.user.email or ""
        name = user.user.user_metadata.get("name") or email.split("@")[0] or "User"
    except Exception:
        return None
    else:
        profile = _get_profile_with_retry(uid)
        roles = profile.roles if profile else ["user"]
        return UserRecord(user_id=uid, email=email, name=name, roles=roles)


def _get_profile_with_retry(uid: str):
    """Fetch UserProfile retrying transient DB connection failures."""
    from time import sleep

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with create_session() as session:
                return session.get(UserProfile, uid)
        except Exception as exc:
            last_error = exc
            sleep(0.5 * (attempt + 1))
    if last_error:
        raise last_error
    return None


def get_current_user(authorization: str | None = Header(default=None)) -> UserRecord:
    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    user = _get_user_from_supabase(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    return user


def get_optional_user(
    authorization: str | None = Header(default=None),
) -> UserRecord | None:
    token = _extract_bearer_token(authorization)
    if token is None:
        return None
    user = _get_user_from_supabase(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    return user


CurrentUser = Annotated[UserRecord, Depends(get_current_user)]
OptionalUser = Annotated[UserRecord | None, Depends(get_optional_user)]


def require_admin(user: CurrentUser) -> UserRecord:
    if "admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role is required.",
        )
    return user


AdminUser = Annotated[UserRecord, Depends(require_admin)]


def require_legal_reviewer(user: CurrentUser) -> UserRecord:
    if "legal_reviewer" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legal reviewer role is required.",
        )
    return user


LegalReviewerUser = Annotated[UserRecord, Depends(require_legal_reviewer)]


def get_db() -> Session:
    with create_session() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
