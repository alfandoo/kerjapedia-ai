from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.api.state import UserRecord, state


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_current_user(authorization: str | None = Header(default=None)) -> UserRecord:
    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    user = state.get_user_by_token(token)
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
    return state.get_user_by_token(token)


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
