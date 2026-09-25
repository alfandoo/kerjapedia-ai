"""Normalized RBAC access helpers + governance seeding.

`user_roles` is authoritative since migration 0016; `UserProfile.roles` JSONB
is kept as a read cache for backward compatibility. All readers go through
:func:`resolve_user_roles` (DB first, JSONB fallback); all writers go through
:func:`set_user_roles` (both stores, single transaction owned by the caller).

:func:`ensure_governance_seeds` idempotently seeds roles, the active prompt
version, and calculator rules from code constants. It runs best-effort at
startup; every resolver falls back to code constants when Neon is bare.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models.business import CalculationRule, PromptVersion, Role, UserProfile, UserRole

logger = logging.getLogger(__name__)

KNOWN_ROLES = ("admin", "legal_reviewer", "user", "guest")


def resolve_user_roles(session: Session, profile: UserProfile | None) -> list[str]:
    """Authoritative role read: `user_roles` rows, else the JSONB cache."""
    if profile is None:
        return ["user"]
    try:
        rows = (
            session.query(UserRole)
            .filter(UserRole.user_id == profile.user_id)
            .all()
        )
    except Exception:
        logger.debug("user_roles lookup failed; using JSONB cache", exc_info=True)
        return list(profile.roles or ["user"])
    if not rows:
        return list(profile.roles or ["user"])
    return sorted({row.role_name for row in rows})


def set_user_roles(
    session: Session,
    user_id: str,
    roles: list[str],
    *,
    assigned_by: str = "system",
) -> list[str]:
    """Write-through: normalize into `user_roles` + refresh the JSONB cache."""
    desired = sorted(set(roles))
    existing_names = {row.name for row in session.query(Role).all()}
    for name in desired:
        if name not in existing_names:
            session.add(Role(name=name, description=""))
    current = {
        row.role_name
        for row in session.query(UserRole).filter(UserRole.user_id == user_id).all()
    }
    for name in desired:
        if name not in current:
            session.add(
                UserRole(user_id=user_id, role_name=name, assigned_by=assigned_by)
            )
    for name in current - set(desired):
        row = (
            session.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role_name == name)
            .first()
        )
        if row is not None:
            session.delete(row)
    profile = session.get(UserProfile, user_id)
    if profile is not None:
        profile.roles = desired
    return desired


def ensure_governance_seeds(session: Session) -> dict[str, int]:
    """Idempotent seeds from code constants; safe to run on every startup."""
    from app.api.state import now_utc

    counts = {"roles": 0, "prompt_versions": 0, "calculation_rules": 0}
    for name in KNOWN_ROLES:
        if session.get(Role, name) is None:
            session.add(Role(name=name, description=""))
            counts["roles"] += 1
    try:
        from app.services.answering.prompts import (
            PROMPT_VERSION_ID,
            SYSTEM_PROMPT,
            USER_TEMPLATE,
        )

        if session.get(PromptVersion, PROMPT_VERSION_ID) is None:
            active = (
                session.query(PromptVersion)
                .filter(PromptVersion.status == "active")
                .first()
            )
            session.add(
                PromptVersion(
                    version_id=PROMPT_VERSION_ID,
                    system_prompt=SYSTEM_PROMPT,
                    user_template=USER_TEMPLATE,
                    status="active" if active is None else "retired",
                    created_by="startup-seed",
                    activated_at=now_utc() if active is None else None,
                )
            )
            counts["prompt_versions"] += 1
    except Exception:
        logger.debug("prompt version seed skipped", exc_info=True)
    try:
        from app.services.calculator.engine import CALCULATOR_RULES

        for rule_type, rule in CALCULATOR_RULES.items():
            rule_id = f"{rule_type}:{rule.version}"
            if session.get(CalculationRule, rule_id) is None:
                session.add(
                    CalculationRule(
                        rule_id=rule_id,
                        rule_type=rule.rule_type,
                        version=rule.version,
                        legal_source=rule.legal_source,
                        effective_from=date.fromisoformat(rule.effective_from),
                        effective_until=(
                            date.fromisoformat(rule.effective_until)
                            if rule.effective_until
                            else None
                        ),
                        formula_identifier=rule.formula_identifier,
                        parameters={},
                        status="active" if rule.status == "active" else "retired",
                    )
                )
                counts["calculation_rules"] += 1
    except Exception:
        logger.debug("calculation rule seed skipped", exc_info=True)
    return counts
