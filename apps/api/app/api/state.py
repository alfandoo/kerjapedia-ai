from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from secrets import token_urlsafe
from threading import Lock
from typing import Any


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class UserRecord:
    user_id: str
    email: str
    name: str
    roles: list[str]


@dataclass
class UserCredentialRecord:
    user: UserRecord
    password_hash: str
    password_salt: str


@dataclass
class ConversationRecord:
    conversation_id: str
    user_id: str
    title: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)


@dataclass
class SessionRecord:
    user: UserRecord
    expires_at: datetime


@dataclass
class ApiState:
    users: dict[str, UserCredentialRecord] = field(default_factory=dict)
    sessions: dict[str, SessionRecord] = field(default_factory=dict)
    conversations: dict[str, ConversationRecord] = field(default_factory=dict)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    ingestion_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    document_admin: dict[str, dict[str, Any]] = field(default_factory=dict)
    uploaded_documents: list[dict[str, Any]] = field(default_factory=list)
    evaluation_datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    evaluation_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    request_counts: dict[str, tuple[int, float]] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def register_user(self, email: str, name: str, password: str) -> UserRecord | None:
        normalized_email = email.strip().lower()
        salt = token_urlsafe(24)
        password_hash = _hash_password(password, salt)
        user = UserRecord(
            user_id=normalized_email,
            email=normalized_email,
            name=name.strip(),
            roles=["user"],
        )
        with self.lock:
            if normalized_email in self.users:
                return None
            self.users[normalized_email] = UserCredentialRecord(
                user=user,
                password_hash=password_hash,
                password_salt=salt,
            )
        return user

    def authenticate_user(self, email: str, password: str) -> UserRecord | None:
        with self.lock:
            credential = self.users.get(email.strip().lower())
        if credential is None:
            return None
        candidate_hash = _hash_password(password, credential.password_salt)
        if not compare_digest(candidate_hash, credential.password_hash):
            return None
        return credential.user

    def create_token(self, user: UserRecord, ttl_minutes: int = 480) -> str:
        token = token_urlsafe(32)
        with self.lock:
            self.sessions[token] = SessionRecord(
                user=user,
                expires_at=now_utc() + timedelta(minutes=ttl_minutes),
            )
        return token

    def revoke_token(self, token: str) -> None:
        with self.lock:
            self.sessions.pop(token, None)

    def get_user_by_token(self, token: str) -> UserRecord | None:
        with self.lock:
            session = self.sessions.get(token)
            if session is None:
                return None
            if session.expires_at <= now_utc():
                self.sessions.pop(token, None)
                return None
            return session.user


state = ApiState()


def _hash_password(password: str, salt: str) -> str:
    return pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        210_000,
    ).hex()
