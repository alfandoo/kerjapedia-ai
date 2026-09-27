"""Bounded, citation-backed conversational pointers; never legal evidence."""

from __future__ import annotations

import re
from typing import Any

from app.services.answering.memory_hardening import redact_retrieval_text
from app.services.retrieval.query import understand_query

_MAX_TURNS = 8
_REFERENCE = re.compile(
    r"\b(yang tadi|yang itu|ketentuannya|bagaimana dengan|gimana dengan|"
    r"what about|how about|that rule|the previous)\b",
    re.I,
)
_AMBIGUOUS = re.compile(r"\b(yang tadi|yang itu|the previous)\b", re.I)


def append_summary(
    summary: dict[str, Any] | None,
    question: str,
    source_message_id: str,
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Append only an already verified, completed cited turn."""
    if not citations:
        return summary or {"version": 1, "turns": []}
    clean, _ = redact_retrieval_text(question)
    turns = list((summary or {}).get("turns") or [])
    document_ids = list(
        dict.fromkeys(
            str(c.get("document_id") or "")[:80] for c in citations if c.get("document_id")
        )
    )[:3]
    articles = list(
        dict.fromkeys(str(c.get("article") or "")[:80] for c in citations if c.get("article"))
    )[:3]
    titles = list(
        dict.fromkeys(
            str(c.get("short_title") or c.get("document_title") or "")[:120]
            for c in citations
            if c.get("short_title") or c.get("document_title")
        )
    )[:3]
    turns.append(
        {
            "source_message_id": source_message_id[:120],
            "question": clean[:240],
            "topics": list(understand_query(question).detected_topics)[:3],
            "document_ids": document_ids,
            "articles": articles,
            "titles": titles,
        }
    )
    return {"version": 1, "turns": turns[-_MAX_TURNS:]}


def summary_context(question: str, summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not _REFERENCE.search(question):
        return None
    if understand_query(question).detected_topics:
        return None
    turns = list((summary or {}).get("turns") or [])
    if not turns:
        return None
    latest = turns[-1]
    if _AMBIGUOUS.search(question) and len(turns) > 1:
        previous = turns[-2]
        if set(previous.get("topics") or []) != set(latest.get("topics") or []) and set(
            previous.get("document_ids") or []
        ) != set(latest.get("document_ids") or []):
            return None
    text = " ".join([str(latest.get("question") or ""), *(latest.get("titles") or [])])
    clean, _ = redact_retrieval_text(text)
    return {
        "text": clean[:400],
        "topics": tuple(latest.get("topics") or []),
        "document_ids": tuple(latest.get("document_ids") or []),
        "articles": tuple(latest.get("articles") or []),
        "source_message_ids": (str(latest.get("source_message_id") or ""),),
    }
