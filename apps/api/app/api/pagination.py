"""Shared admin list pagination — backward-compatible by design.

Endpoints keep returning plain JSON lists ordered newest-first.
`limit=None` preserves the legacy shape (capped server-side at LEGACY_CAP);
otherwise the slice happens in SQL and the total is exposed via
`X-Total-Count` so UIs can page without a second round-trip.
"""

from __future__ import annotations

DEFAULT_LIMIT = 100
MAX_LIMIT = 500
LEGACY_CAP = 1000


def clamp_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    return max(1, min(int(limit), MAX_LIMIT))


def clamp_offset(offset: int) -> int:
    return max(0, int(offset or 0))


def apply_db_pagination(query, limit: int | None, offset: int):
    """Apply OFFSET/LIMIT in SQL; legacy None limit becomes a server cap."""
    offset = clamp_offset(offset)
    limit = clamp_limit(limit)
    if offset:
        query = query.offset(offset)
    if limit is None:
        return query.limit(LEGACY_CAP)
    return query.limit(limit)
