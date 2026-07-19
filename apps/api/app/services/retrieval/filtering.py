from __future__ import annotations

from typing import Any

from app.services.retrieval.schemas import RetrievalDocument


def matches_filters(document: RetrievalDocument, filters: dict[str, Any]) -> bool:
    article = filters.get("article")
    if article and document.article != article:
        return False

    year = filters.get("year")
    if year and document.metadata.get("year") != year:
        return False

    topics = filters.get("topics")
    if topics and not set(topics).intersection(document.topics):
        return False

    regulation_type = filters.get("regulation_type")
    if regulation_type and document.metadata.get("regulation_type") != regulation_type:
        return False

    status = filters.get("legal_status")
    if status and document.legal_status != status:
        return False

    return True
