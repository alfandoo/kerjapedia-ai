"""Freshness: verification decays, and stale status demotes ranking.

A document verified long ago (or never) must not rank like a freshly
verified one. This module only reports the state; retrieval decides how
to demote.
"""

from __future__ import annotations

from datetime import datetime

from app.services.rag.collection.schemas import FreshnessStatus


def evaluate_freshness(
    last_verified_at: datetime | None,
    now: datetime,
    *,
    due_days: int = 90,
    stale_days: int = 180,
) -> FreshnessStatus:
    """Classify verification freshness from the last verification time."""
    if last_verified_at is None:
        return FreshnessStatus(
            state="due",
            days_since_verification=None,
            action="verify_before_production_use",
        )
    days = (now - last_verified_at).days
    if days <= due_days:
        return FreshnessStatus(state="fresh", days_since_verification=days, action="none")
    if days <= stale_days:
        return FreshnessStatus(
            state="due",
            days_since_verification=days,
            action="schedule_reverification",
        )
    return FreshnessStatus(
        state="stale",
        days_since_verification=days,
        action="demote_in_ranking",
    )
