from __future__ import annotations

from urllib.parse import urlparse


def is_canonical_official_source_url(value: str | None) -> bool:
    """Return True only for HTTPS URLs hosted on an official Indonesian government
    (.go.id) domain.

    Search-style government URLs (e.g. peraturan.bpk.go.id/Search?... ) are accepted
    because they are deterministic, government-hosted regulation pages. Non-government
    hosts (search engines, blogs, storage providers) are still rejected.
    """
    if not value:
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host:
        return False
    return host.endswith(".go.id") or host == "go.id"
