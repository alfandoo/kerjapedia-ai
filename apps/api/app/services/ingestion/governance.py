from __future__ import annotations

from urllib.parse import urlparse


def is_canonical_official_source_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if parsed.scheme != "https" or not host or "/search" in path:
        return False
    return host.endswith(".go.id") or host == "go.id"
