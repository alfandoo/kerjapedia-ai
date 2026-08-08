from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.api.state import now_utc
from app.db.session import create_session
from app.models.business import AuditLog


def log_audit(
    actor: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        with create_session() as session:
            session.add(
                AuditLog(
                    audit_id=f"aud_{uuid4().hex}",
                    actor=actor,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    details=details or {},
                    created_at=now_utc(),
                )
            )
            session.commit()
    except Exception:
        pass


def list_audit_logs(session, limit: int = 100) -> list[dict]:
    rows = (
        session.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [
        {
            "audit_id": row.audit_id,
            "actor": row.actor,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "details": row.details,
            "created_at": row.created_at,
        }
        for row in rows
    ]
