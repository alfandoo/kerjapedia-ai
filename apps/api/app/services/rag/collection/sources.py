"""Source registry, official-URL gate, and connector interface.

Connectors (e.g. a scheduled BPK crawler) plug in through the
:class:`Connector` protocol; the registry only records what happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

from app.services.rag.collection.schemas import SourceRecord


@dataclass(frozen=True)
class FetchedFile:
    """One file delivered by a connector."""

    file_name: str
    content: bytes
    source_url: str
    fetched_at: datetime
    origin: str = "connector"


class Connector(Protocol):
    """Scheduled source of documents. Implementations poll; the registry
    records."""

    @property
    def source_id(self) -> str: ...

    def poll(self) -> list[FetchedFile]: ...


class SourceRegistry:
    """Known origins with trust scores. Unknown sources are distrusted."""

    def __init__(self, sources: list[SourceRecord] | None = None) -> None:
        self._sources: dict[str, SourceRecord] = {}
        for source in sources or []:
            self.register(source)

    def register(self, source: SourceRecord) -> None:
        self._sources[source.source_id] = source

    def get(self, source_id: str) -> SourceRecord | None:
        return self._sources.get(source_id)

    def trust_of(self, source_id: str) -> float:
        source = self._sources.get(source_id)
        if source is None or not source.enabled:
            return 0.0
        return source.trust_score

    def is_official_url(self, url: str | None) -> bool:
        """Accept HTTPS URLs on an enabled source's allowed domains only."""
        if not url:
            return False
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        for source in self._sources.values():
            if not source.enabled:
                continue
            for domain in source.allowed_domains:
                domain = domain.lower()
                if host == domain or host.endswith("." + domain):
                    return True
        return False
