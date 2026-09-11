from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Header, HTTPException, Query, status
from supabase_auth.errors import AuthApiError

from app.api.dependencies import CurrentUser, DbSession, _extract_bearer_token
from app.api.schemas import (
    EmailOtpVerifyRequest,
    EmailResendRequest,
    GoogleAuthRequest,
    LoginMethodsResponse,
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
from app.models.business import (
    Conversation,
    Feedback,
    Message,
    PendingRegistration,
    UserProfile,
)
from app.services import supabase as supabase_service
from app.services.mailer import send_verification_email

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


def _google_email_verified(id_token: str) -> bool:
    """Read the `email_verified` claim from a Google ID token.

    The token signature is validated upstream by Supabase
    (`sign_in_with_id_token`). We only inspect the already-trusted claim.
    Fails closed (returns False) on any decoding error.
    """
    try:
        payload = pyjwt.decode(id_token, options={"verify_signature": False})
        return bool(payload.get("email_verified", False))
    except Exception:
        return False


def _lookup_login_methods(email: str) -> tuple[bool, bool, list[str]]:
    """Determine whether an email belongs to a known user and whether it has a
    password, by scanning Supabase admin users (bounded pagination)."""
    email = email.lower()
    try:
        supabase = supabase_service.get_supabase()
        # Bounded scan; list_users pages forward by per_page. A generous cap
        # keeps this safe in MVP while covering reasonable user counts.
        page = 0
        per_page = 200
        for _ in range(50):  # up to 10k users
            users = supabase.auth.admin.list_users(page=page, per_page=per_page) or []
            for user in users:
                if (user.email or "").lower() == email:
                    providers = list(user.app_metadata.get("providers") or [])
                    has_password = "email" in providers or "password" in providers
                    return True, has_password, providers
            if len(users) < per_page:
                break
            page += 1
        return False, False, []
    except Exception:
        # On any lookup failure, fall back to "unknown" so login can proceed
        # normally instead of blocking the user.
        return False, False, []


def _generate_otp() -> str:
    return f"{secrets.randbelow(10**8):08d}"


def _otp_hash(email: str, code: str) -> str:
    digest = hmac.new(
        settings.secret_key.encode(), f"{email.lower()}:{code}".encode(), hashlib.sha256
    )
    return digest.hexdigest()


def _otp_valid(email: str, code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(_otp_hash(email, code), expected_hash)


def _fernet() -> Fernet:
    return Fernet(settings.secret_key.encode())


_SESSION_CREATE_FAILED = (
    "Akun berhasil dibuat, namun sesi belum dapat dibuat. Silakan masuk kembali."
)


def _purge_expired_pending(session) -> None:
    """Delete expired pending registrations so the table never accumulates."""
    session.query(PendingRegistration).filter(
        PendingRegistration.expires_at < datetime.now(UTC)
    ).delete(synchronize_session=False)
    # Drop any pending row whose email already belongs to a confirmed user;
    # those can never be verified again, so they are stale.
    confirmed_emails = session.query(UserProfile.email).subquery()
    session.query(PendingRegistration).filter(
        PendingRegistration.email.in_(confirmed_emails)
    ).delete(synchronize_session=False)


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
    """Start a deferred email signup. No Supabase user is created yet; an OTP
    email is sent and the user is only created after the code is verified."""
    try:
        code = _generate_otp()
        encrypted = _fernet().encrypt(payload.password.encode("utf-8")).decode("ascii")
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.email_otp_expiry_minutes)
        with create_session() as session:
            _purge_expired_pending(session)
            existing = (
                session.query(UserProfile)
                .filter(UserProfile.email == payload.email.lower())
                .first()
            )
            if existing is not None:
                # Persist the stale-pending cleanup even though this signup
                # is rejected as a duplicate.
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email sudah terdaftar.",
                )
            pending = session.get(PendingRegistration, payload.email.lower())
            if pending is None:
                pending = PendingRegistration(
                    email=payload.email.lower(),
                    name=payload.name,
                    password_encrypted=encrypted,
                    otp_hash=_otp_hash(payload.email.lower(), code),
                    attempts=0,
                    expires_at=expires_at,
                )
                session.add(pending)
            else:
                pending.name = payload.name
                pending.password_encrypted = encrypted
                pending.otp_hash = _otp_hash(payload.email.lower(), code)
                pending.attempts = 0
                pending.expires_at = expires_at
                pending.created_at = datetime.now(UTC)
            session.commit()
        try:
            send_verification_email(payload.email.lower(), code)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Kode verifikasi gagal dikirim. Silakan coba lagi.",
            ) from exc
        return LoginResponse(
            access_token="",
            refresh_token="",
            user=UserResponse(
                user_id="",
                email=payload.email.lower(),
                name=payload.name,
                roles=[],
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registrasi gagal. Silakan coba lagi.",
        ) from exc


@router.get("/login-methods", response_model=LoginMethodsResponse)
def login_methods(email: str = Query(min_length=3, max_length=160)) -> LoginMethodsResponse:
    """Report which sign-in methods exist for an email, so the UI can either
    offer Google or keep the password form instead of a confusing error."""
    exists, has_password, providers = _lookup_login_methods(email.lower())
    return LoginMethodsResponse(
        email_exists=exists,
        has_password=has_password,
        providers=providers,
    )


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
        # Security: never auto-link an account based on an unverified email.
        if not _google_email_verified(payload.id_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Email Google belum terverifikasi. "
                    "Gunakan akun Google dengan email terverifikasi."
                ),
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


@router.post("/verify-email-otp", response_model=LoginResponse)
def verify_email_otp(payload: EmailOtpVerifyRequest) -> LoginResponse:
    """Validate the OTP, then (and only then) create the Supabase user."""
    email = payload.email.lower()
    with create_session() as session:
        pending = session.get(PendingRegistration, email)
        if pending is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kode verifikasi salah atau telah kedaluwarsa.",
            )
        if datetime.now(UTC) > pending.expires_at:
            session.delete(pending)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kode verifikasi telah kedaluwarsa. Silakan kirim ulang.",
            )
        if not _otp_valid(email, payload.token, pending.otp_hash):
            pending.attempts = int(pending.attempts) + 1
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kode verifikasi salah.",
            )
        if int(pending.attempts) > 8:
            session.delete(pending)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Terlalu banyak percobaan. Silakan kirim ulang kode.",
            )
        encrypted_password = pending.password_encrypted
        name = pending.name
        session.delete(pending)
        session.commit()
    try:
        password = _fernet().decrypt(encrypted_password.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sesi pendaftaran tidak valid. Silakan daftar ulang.",
        ) from None
    try:
        created = supabase_service.get_supabase().auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "user_metadata": {"name": name},
                "email_confirm": True,
            }
        )
        uid = created.user.id
        record = _sync_user_profile(uid, email, name)
    except HTTPException:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "already registered" in err or "already exists" in err:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email sudah terdaftar.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pendaftaran gagal. Silakan coba lagi.",
        ) from exc
    # Log the user in so a fresh session is issued to the app.
    try:
        result = supabase_service.get_supabase_anon().auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        access_token, refresh_token = _session_tokens(result.session)
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_SESSION_CREATE_FAILED,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_SESSION_CREATE_FAILED,
        ) from exc
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=to_user_response(record),
    )


@router.post("/resend-otp")
def resend_otp(payload: EmailResendRequest) -> dict[str, str]:
    """Regenerate and resend the OTP for an existing pending signup."""
    email = payload.email.lower()
    with create_session() as session:
        _purge_expired_pending(session)
        pending = session.get(PendingRegistration, email)
        if pending is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Belum ada pendaftaran untuk email ini.",
            )
        code = _generate_otp()
        pending.otp_hash = _otp_hash(email, code)
        pending.attempts = 0
        pending.expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.email_otp_expiry_minutes
        )
        session.commit()
    try:
        send_verification_email(email, code)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Kode verifikasi belum dapat dikirim ulang. Silakan coba lagi."
        ) from exc
    return {"status": "resent"}


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
