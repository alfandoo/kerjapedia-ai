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


def _get_user_from_supabase(token: str) -> UserRecord | None:
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
        with create_session() as session:
            profile = session.get(UserProfile, uid)
            roles = profile.roles if profile else ["user"]
        return UserRecord(user_id=uid, email=email, name=name, roles=roles)


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
    return _get_user_from_supabase(token)


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


def get_db() -> Session:
    with create_session() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
