from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from app.api.dependencies import CurrentUser, _extract_bearer_token
from app.api.schemas import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.api.state import UserRecord
from app.core.config import settings
from app.db.session import create_session
from app.models.business import UserProfile
from app.services import supabase as supabase_service

router = APIRouter(prefix="/auth", tags=["auth"])


def to_user_response(user: UserRecord) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        roles=user.roles,
    )


def _sync_user_profile(
    uid: str, email: str, name: str, roles: list[str] | None = None
) -> UserRecord:
    resolved_roles = roles or (["admin", "user"] if email == settings.admin_email else ["user"])
    with create_session() as session:
        profile = session.get(UserProfile, uid)
        if profile is None:
            existing = session.query(UserProfile).filter(
                UserProfile.email == email
            ).first()
            if existing:
                existing.user_id = uid
                existing.name = name
                existing.roles = resolved_roles
                profile = existing
            else:
                profile = UserProfile(
                    user_id=uid,
                    email=email,
                    name=name,
                    roles=resolved_roles,
                )
                session.add(profile)
        else:
            profile.email = email
            profile.name = name
            profile.roles = resolved_roles
        session.commit()
    return UserRecord(user_id=uid, email=email, name=name, roles=resolved_roles)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    with create_session() as session:
        profile_exists = session.query(UserProfile).filter(
            UserProfile.email == payload.email
        ).first() is not None
        if not profile_exists:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email belum terdaftar.",
            )
    try:
        supabase = supabase_service.get_supabase_anon()
        result = supabase.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
        user = result.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email atau password salah.",
            )
        uid = user.id
        email = user.email or payload.email
        name = user.user_metadata.get("name") or email.split("@")[0]
        record = _sync_user_profile(uid, email, name)
        return LoginResponse(
            access_token=result.session.access_token if result.session else "",
            user=to_user_response(record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah.",
        ) from exc


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> LoginResponse:
    try:
        supabase = supabase_service.get_supabase_anon()
        result = supabase.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {"data": {"name": payload.name}},
            }
        )
        user = result.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email sudah terdaftar.",
            )
        uid = user.id
        record = _sync_user_profile(uid, payload.email, payload.name)
        if result.session:
            return LoginResponse(
                access_token=result.session.access_token,
                user=to_user_response(record),
            )
        return LoginResponse(
            access_token="",
            user=to_user_response(record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email sudah terdaftar atau registrasi gagal.",
        ) from exc


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, str]:
    token = _extract_bearer_token(authorization)
    if token:
        try:
            supabase = supabase_service.get_supabase_anon()
            supabase.auth.admin.sign_out(token)
        except Exception:
            pass
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> UserResponse:
    return to_user_response(user)
