from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class UserRecord:
    user_id: str
    email: str
    name: str
    roles: list[str]


@dataclass
class ApiState:
    request_counts: dict[str, tuple[int, float]] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)


state = ApiState()
