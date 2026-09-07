from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from supabase_auth.errors import AuthApiError

from app.api.dependencies import CurrentUser, DbSession, _extract_bearer_token
from app.api.schemas import (
    GoogleAuthRequest,
    LoginRequest,
    LoginResponse,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
)
from app.api.state import UserRecord
from app.core.config import settings
from app.db.session import create_session
from app.models.business import Conversation, Feedback, Message, UserProfile
from app.services import supabase as supabase_service

router = APIRouter(prefix="/auth", tags=["auth"])


def to_user_response(user: UserRecord) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        roles=user.roles,
    )


def _session_tokens(session) -> tuple[str, str]:
    if session is None:
        return "", ""
    access_token = getattr(session, "access_token", None) or ""
    refresh_token = getattr(session, "refresh_token", None) or ""
    return str(access_token), str(refresh_token)


def _sync_user_profile(
    uid: str, email: str, name: str, roles: list[str] | None = None
) -> UserRecord:
    default_roles = (
        ["admin", "legal_reviewer", "user"] if email == settings.admin_email else ["user"]
    )
    with create_session() as session:
        profile = session.get(UserProfile, uid)
        if profile is None:
            existing = session.query(UserProfile).filter(UserProfile.email == email).first()
            if existing:
                resolved_roles = roles or list(existing.roles) or default_roles
                if email == settings.admin_email:
                    resolved_roles = sorted(
                        set(resolved_roles).union({"admin", "legal_reviewer", "user"})
                    )
                existing.user_id = uid
                existing.name = name
                existing.roles = resolved_roles
                profile = existing
            else:
                resolved_roles = roles or default_roles
                profile = UserProfile(
                    user_id=uid,
                    email=email,
                    name=name,
                    roles=resolved_roles,
                )
                session.add(profile)
        else:
            resolved_roles = roles or list(profile.roles) or default_roles
            if email == settings.admin_email:
                resolved_roles = sorted(
                    set(resolved_roles).union({"admin", "legal_reviewer", "user"})
                )
            profile.email = email
            profile.name = name
            profile.roles = resolved_roles
        session.commit()
    return UserRecord(user_id=uid, email=email, name=name, roles=resolved_roles)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
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
        access_token, refresh_token = _session_tokens(result.session)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=to_user_response(record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah.",
        ) from exc


@router.post("/refresh", response_model=LoginResponse)
def refresh(payload: RefreshRequest) -> LoginResponse:
    try:
        supabase = supabase_service.get_supabase_anon()
        result = supabase.auth.refresh_session(payload.refresh_token)
        user = result.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesi telah berakhir. Silakan masuk kembali.",
            )
        uid = user.id
        email = user.email or ""
        name = user.user_metadata.get("name") or email.split("@")[0] or "User"
        record = _sync_user_profile(uid, email, name)
        access_token, refresh_token = _session_tokens(result.session)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=to_user_response(record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi telah berakhir. Silakan masuk kembali.",
        ) from exc


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> LoginResponse:
    with create_session() as session:
        existing = session.query(UserProfile).filter(UserProfile.email == payload.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email sudah terdaftar.",
            )
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
        if result.session:
            uid = user.id
            record = _sync_user_profile(uid, payload.email, payload.name)
            access_token, refresh_token = _session_tokens(result.session)
            return LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                user=to_user_response(record),
            )
        uid = user.id
        record = _sync_user_profile(uid, payload.email, payload.name)
        return LoginResponse(
            access_token="",
            refresh_token="",
            user=to_user_response(record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "already registered" in err or "already exists" in err:
            try:
                supabase = supabase_service.get_supabase_anon()
                result = supabase.auth.sign_in_with_password(
                    {"email": payload.email, "password": payload.password}
                )
                user = result.user
                if user:
                    uid = user.id
                    record = _sync_user_profile(uid, payload.email, payload.name)
                    access_token, refresh_token = _session_tokens(result.session)
                    return LoginResponse(
                        access_token=access_token,
                        refresh_token=refresh_token,
                        user=to_user_response(record),
                    )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email sudah terdaftar.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registrasi gagal. Silakan coba lagi.",
        ) from exc


@router.post("/google", response_model=LoginResponse)
def google_login(payload: GoogleAuthRequest) -> LoginResponse:
    """Exchange a Google ID token (from Google Identity Services) for a Supabase session."""
    try:
        supabase = supabase_service.get_supabase_anon()
        result = supabase.auth.sign_in_with_id_token(
            {"provider": "google", "token": payload.id_token}
        )
        user = result.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Autentikasi Google gagal.",
            )
        uid = user.id
        email = user.email or ""
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akun Google tidak memiliki email.",
            )
        name = user.user_metadata.get("name") or email.split("@")[0] or "User"
        record = _sync_user_profile(uid, email, name)
        access_token, refresh_token = _session_tokens(result.session)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=to_user_response(record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentikasi Google gagal. Silakan coba lagi.",
        ) from exc


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, str]:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    try:
        supabase = supabase_service.get_supabase()
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")
        # The SDK expects the caller's access JWT, not the user's UUID.
        supabase.auth.admin.sign_out(token, scope="global")
    except HTTPException:
        raise
    except AuthApiError as exc:
        if exc.status in (401, 403, 404):
            raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
        raise HTTPException(status_code=503, detail="Logout gagal. Silakan coba lagi.") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Logout gagal. Silakan coba lagi.") from exc
    return {"status": "ok"}


@router.delete("/account")
def delete_account(user: CurrentUser, session: DbSession) -> dict[str, str]:
    """Permanently delete the authenticated user's account and personal data."""
    try:
        # Remove conversations and their messages first (messages reference conversations).
        owned = (
            session.query(Conversation)
            .filter(Conversation.user_id == user.user_id)
            .all()
        )
        owned_ids = [item.conversation_id for item in owned]
        if owned_ids:
            session.query(Message).filter(
                Message.conversation_id.in_(owned_ids)
            ).delete(synchronize_session=False)
            session.query(Conversation).filter(
                Conversation.conversation_id.in_(owned_ids)
            ).delete(synchronize_session=False)
        # Anonymize feedback rows (no FK, keep aggregate value without identity).
        session.query(Feedback).filter(Feedback.user_id == user.user_id).update(
            {Feedback.user_id: None}, synchronize_session=False
        )
        profile = session.get(UserProfile, user.user_id)
        if profile is not None:
            session.delete(profile)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=503, detail="Akun belum dapat dihapus. Silakan coba lagi."
        ) from exc
    try:
        supabase = supabase_service.get_supabase()
        supabase.auth.admin.delete_user(user.user_id)
    except AuthApiError as exc:
        if exc.status not in (401, 403, 404):
            raise HTTPException(
                status_code=503, detail="Akun belum dapat dihapus. Silakan coba lagi."
            ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Akun belum dapat dihapus. Silakan coba lagi."
        ) from exc
    return {"status": "deleted"}


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> UserResponse:
    return to_user_response(user)


@router.patch("/profile", response_model=UserResponse)
def update_profile(payload: ProfileUpdateRequest, user: CurrentUser, session: DbSession):
    try:
        # The authenticated ID is the only target; never accept roles/email/ID from JSON.
        supabase_service.get_supabase().auth.admin.update_user_by_id(
            user.user_id, {"user_metadata": {"name": payload.name}}
        )
        profile = session.get(UserProfile, user.user_id)
        if profile is None:
            profile = UserProfile(
                user_id=user.user_id, email=user.email, name=payload.name, roles=user.roles
            )
            session.add(profile)
        else:
            profile.name = payload.name
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail="Profil belum dapat disimpan.") from exc
    return UserResponse(user_id=user.user_id, email=user.email, name=payload.name, roles=user.roles)
