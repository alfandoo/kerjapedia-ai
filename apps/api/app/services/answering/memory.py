from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.retrieval.query import understand_query

_FOLLOW_UP_PATTERN = re.compile(
    r"^(kalau|jika|lalu|terus|bagaimana dengan|gimana dengan|berapa|apakah itu)\b|"
    r"\b(ini|itu|tersebut|tadi|yang sama)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MemoryContext:
    retrieval_query: str
    used: bool
    source_turns: int


def build_memory_context(
    question: str,
    messages: list[dict[str, Any]],
    max_user_turns: int = 2,
    max_chars: int = 600,
) -> MemoryContext:
    understanding = understand_query(question)
    needs_context = not understanding.detected_topics and bool(_FOLLOW_UP_PATTERN.search(question))
    if not needs_context:
        return MemoryContext(retrieval_query=question, used=False, source_turns=0)

    previous_questions = [
        str(message["content"]).strip()
        for message in reversed(messages)
        if message.get("role") == "user" and str(message.get("content", "")).strip()
    ][:max_user_turns]
    previous_questions.reverse()
    if not previous_questions:
        return MemoryContext(retrieval_query=question, used=False, source_turns=0)

    context = " ".join(previous_questions)
    context = context[-max_chars:]
    return MemoryContext(
        retrieval_query=f"{context} Pertanyaan lanjutan: {question}",
        used=True,
        source_turns=len(previous_questions),
    )
