from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
