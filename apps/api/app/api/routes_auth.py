from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from app.api.dependencies import CurrentUser, _extract_bearer_token
from app.api.schemas import LoginRequest, LoginResponse, UserResponse
from app.api.state import UserRecord, state

router = APIRouter(prefix="/auth", tags=["auth"])


def to_user_response(user: UserRecord) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        roles=user.roles,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if not payload.password.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is required.",
        )

    roles = ["user"]
    if payload.email.lower().startswith("admin@"):
        roles.append("admin")

    user = UserRecord(
        user_id=payload.email.lower(),
        email=payload.email.lower(),
        name=payload.email.split("@")[0],
        roles=roles,
    )
    token = state.create_token(user)
    return LoginResponse(access_token=token, user=to_user_response(user))


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, str]:
    token = _extract_bearer_token(authorization)
    if token:
        state.revoke_token(token)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> UserResponse:
    return to_user_response(user)
