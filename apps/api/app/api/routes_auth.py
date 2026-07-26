from __future__ import annotations

from hmac import compare_digest

from fastapi import APIRouter, Header, HTTPException, status

from app.api.dependencies import CurrentUser, _extract_bearer_token
from app.api.schemas import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.api.state import UserRecord, state
from app.core.config import settings

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

    email = payload.email.lower()
    is_admin_email = compare_digest(email, settings.admin_email.lower())
    is_admin_password = compare_digest(payload.password, settings.admin_password)
    if is_admin_email and not is_admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    if is_admin_email and is_admin_password:
        user = UserRecord(
            user_id=email,
            email=email,
            name=payload.email.split("@")[0],
            roles=["user", "admin"],
        )
    else:
        user = state.authenticate_user(email, payload.password)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email atau password salah.",
            )
    token = state.create_token(user, ttl_minutes=settings.session_ttl_minutes)
    return LoginResponse(access_token=token, user=to_user_response(user))


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> LoginResponse:
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Alamat email tidak valid.",
        )
    if email == settings.admin_email.lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email sudah terdaftar.",
        )
    user = state.register_user(email, name, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email sudah terdaftar.",
        )
    token = state.create_token(user, ttl_minutes=settings.session_ttl_minutes)
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
