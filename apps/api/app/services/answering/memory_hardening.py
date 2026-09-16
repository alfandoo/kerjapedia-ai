from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.answering.generator import _detect_language
from app.services.answering.schemas import HistoryTurn
from app.services.retrieval.query import is_employment_query, understand_query

_EXPLICIT_FOLLOW_UP_PATTERN = re.compile(
    r"^(kalau|jika|lalu|terus|bagaimana dengan|gimana dengan|"
    r"what about|how about|and what|then)\b",
    re.IGNORECASE,
)
# Referential follow-ups are detected by shape, not by vocabulary. Indonesian
# marks given information with the enclitic -nya (ketentuannya, dendanya,
# konsekuensinya, ...) or a demonstrative (ini/itu/tersebut), so any noun
# works without maintaining a stem allowlist. Only monomorphemic lookalikes
# that are never referential are excluded (hanya = "only", tanya-family =
# the verb "to ask").
_NYA_WORD_PATTERN = re.compile(r"\b([a-z]+nya|nya)\b", re.IGNORECASE)
_NYA_NON_REFERENTIAL_WORDS = frozenset(
    {"hanya", "tanya", "bertanya", "ditanya", "menanya"}
)
_DEMONSTRATIVE_PATTERN = re.compile(
    r"\b(ini|itu|tersebut)\b|"
    r"\bhal (?:ini|itu|tersebut)\b|"
    r"\byang (?:ini|itu|tersebut|sama|mana)\b|"
    r"\b(the penalty|the sanction|the payment|that payment|their rights?|"
    r"its rules?|what about it|how about that)\b",
    re.IGNORECASE,
)
_ELLIPTICAL_FOLLOW_UP_PATTERN = re.compile(
    r"^(dibayar|dibayarkan|diberikan|diterima|diserahkan|disetor|dikelola|"
    r"untuk siapa|ke siapa|kepada siapa|oleh siapa|berapa besar|berapa lama|"
    r"who receives|who gets|who pays|where is|where does|how much|how long)\b",
    re.IGNORECASE,
)
_NON_EMPLOYMENT_SWITCH_PATTERN = re.compile(
    r"\b(pajak|saham|kripto|kendaraan|presiden|pemilu|cuaca|resep|"
    r"tax|stock|crypto|vehicle|president|election|weather|recipe)(?:nya)?\b",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])")
_NIK_PATTERN = re.compile(r"(?<!\d)\d{16}(?!\d)")
_PHONE_PATTERN = re.compile(r"(?<![\w\d])(?:\+62|62|0)[\s.-]?(?:\d[\s.-]?){8,13}\d(?![\w\d])")
_SECRET_PATTERN = re.compile(
    r"(?i)\b(bearer|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|token)"
    r"\s*[:=]?\s*([A-Za-z0-9._~+/=-]{8,})"
)


@dataclass(frozen=True)
class MemoryContext:
    original_question: str
    retrieval_query: str
    used: bool
    source_turns: int
    activation_reason: str | None = None
    citation_context: tuple[str, ...] = ()
    question_language: str = "id"
    context_topics: tuple[str, ...] = ()
    context_document_ids: tuple[str, ...] = ()
    context_articles: tuple[str, ...] = ()
    source_message_ids: tuple[str, ...] = ()
    redaction_count: int = 0


@dataclass(frozen=True)
class _EligibleTurn:
    question: str
    user_message_id: str | None
    topics: tuple[str, ...]
    document_ids: tuple[str, ...]
    articles: tuple[str, ...]
    citation_descriptors: tuple[str, ...]


def _metadata(message: dict[str, Any]) -> dict[str, Any]:
    metadata = message.get("metadata") or message.get("meta_data") or {}
    return metadata if isinstance(metadata, dict) else {}


def _guardrail_allowed(message: dict[str, Any]) -> bool:
    metadata = _metadata(message)
    if metadata.get("memory_eligible") is False:
        return False
    if metadata.get("turn_status") in {"processing", "failed", "abandoned"}:
        return False
    rag_trace = metadata.get("rag_trace") or {}
    if not isinstance(rag_trace, dict):
        return True
    guardrail = rag_trace.get("guardrail") or {}
    return not isinstance(guardrail, dict) or guardrail.get("allowed") is not False


def _answer_citations(message: dict[str, Any]) -> list[dict[str, Any]]:
    answer = _metadata(message).get("answer")
    if not isinstance(answer, dict):
        return []
    if answer.get("answer_status", "answered") != "answered":
        return []
    if answer.get("refusal_reason"):
        return []
    citations = answer.get("citations")
    if not isinstance(citations, list):
        return []
    return [citation for citation in citations if isinstance(citation, dict)]


def _citation_values(
    citations: list[dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    descriptors: list[str] = []
    document_ids: list[str] = []
    articles: list[str] = []
    for citation in citations:
        descriptor = str(
            citation.get("short_title") or citation.get("document_title") or ""
        ).strip()
        document_id = str(citation.get("document_id") or "").strip()
        article = str(citation.get("article") or "").strip()
        if descriptor and descriptor not in descriptors:
            descriptors.append(descriptor)
        if document_id and document_id not in document_ids:
            document_ids.append(document_id)
        if article and article not in articles:
            articles.append(article)
    return tuple(descriptors[:3]), tuple(document_ids[:3]), tuple(articles[:3])


def _eligible_turns(messages: list[dict[str, Any]]) -> list[_EligibleTurn]:
    turns: list[_EligibleTurn] = []
    pending_user: dict[str, Any] | None = None
    for message in messages:
        role = message.get("role")
        if role == "user":
            pending_user = message
            continue
        if role != "assistant" or pending_user is None:
            continue
        user = pending_user
        pending_user = None
        question = str(user.get("content") or "").strip()
        citations = _answer_citations(message)
        if not question or not citations or not _guardrail_allowed(user):
            continue
        descriptors, document_ids, articles = _citation_values(citations)
        turns.append(
            _EligibleTurn(
                question=question,
                user_message_id=(str(user.get("message_id")) if user.get("message_id") else None),
                topics=tuple(understand_query(question).detected_topics),
                document_ids=document_ids,
                articles=articles,
                citation_descriptors=descriptors,
            )
        )
    return turns


def _turns_are_coherent(older: _EligibleTurn, newer: _EligibleTurn) -> bool:
    older_topics = set(older.topics)
    newer_topics = set(newer.topics)
    if older_topics and newer_topics:
        return bool(older_topics.intersection(newer_topics))
    return bool(set(older.document_ids).intersection(newer.document_ids))


def _has_referential_signal(question: str) -> bool:
    """True when the question visibly points at prior context.

    Accepts any -nya suffixed word (minus a tiny exclusion set) and any
    demonstrative, so new nouns like "ketentuannya" or "konsekuensinya"
    work with no vocabulary maintenance.
    """
    if _DEMONSTRATIVE_PATTERN.search(question):
        return True
    for match in _NYA_WORD_PATTERN.finditer(question):
        if match.group(1).lower() not in _NYA_NON_REFERENTIAL_WORDS:
            return True
    return False


def _activation_reason(question: str) -> str | None:
    if _has_referential_signal(question):
        return "referential_term"
    if len(question.split()) <= 8 and _ELLIPTICAL_FOLLOW_UP_PATTERN.search(question):
        return "elliptical_follow_up"
    if len(question.split()) <= 12 and _EXPLICIT_FOLLOW_UP_PATTERN.search(question):
        return "explicit_marker"
    return None


def redact_retrieval_text(text: str) -> tuple[str, int]:
    redacted = text
    total = 0
    for pattern, replacement in (
        (_EMAIL_PATTERN, "[REDACTED_EMAIL]"),
        (_NIK_PATTERN, "[REDACTED_ID]"),
        (_PHONE_PATTERN, "[REDACTED_PHONE]"),
    ):
        redacted, count = pattern.subn(replacement, redacted)
        total += count

    def replace_secret(match: re.Match[str]) -> str:
        return f"{match.group(1)} [REDACTED_SECRET]"

    redacted, count = _SECRET_PATTERN.subn(replace_secret, redacted)
    return redacted, total + count


def _truncate_head_at_word(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    candidate = text[:limit].rstrip()
    if limit < len(text) and not text[limit].isspace() and " " in candidate:
        candidate = candidate.rsplit(" ", 1)[0]
    return candidate.strip()


def _truncate_tail_at_word(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    candidate = text[-limit:].lstrip()
    if len(text) > limit and not text[-limit - 1].isspace() and " " in candidate:
        candidate = candidate.split(" ", 1)[1]
    return candidate.strip()


def _base_context(question: str, max_chars: int, question_language: str) -> MemoryContext:
    sanitized, redaction_count = redact_retrieval_text(question)
    return MemoryContext(
        original_question=question,
        retrieval_query=_truncate_head_at_word(sanitized, max_chars),
        used=False,
        source_turns=0,
        question_language=question_language,
        redaction_count=redaction_count,
    )


def build_memory_context(
    question: str,
    messages: list[dict[str, Any]],
    max_user_turns: int = 2,
    max_chars: int = 600,
) -> MemoryContext:
    question_language = _detect_language(question)
    base = _base_context(question, max_chars, question_language)
    current_understanding = understand_query(question)
    if (
        current_understanding.detected_topics
        or is_employment_query(current_understanding)
        or _NON_EMPLOYMENT_SWITCH_PATTERN.search(question)
    ):
        return base

    reason = _activation_reason(question)
    if reason is None:
        return base
    eligible = _eligible_turns(messages)
    if not eligible:
        return base
    selected = [eligible[-1]]
    if max_user_turns > 1 and len(eligible) > 1:
        previous = eligible[-2]
        if _turns_are_coherent(previous, eligible[-1]):
            selected.insert(0, previous)
    selected = selected[-max(1, max_user_turns) :]

    topics = tuple(dict.fromkeys(topic for turn in selected for topic in turn.topics))
    document_ids = tuple(
        dict.fromkeys(document_id for turn in selected for document_id in turn.document_ids)
    )
    articles = tuple(dict.fromkeys(article for turn in selected for article in turn.articles))
    descriptors = tuple(
        dict.fromkeys(descriptor for turn in selected for descriptor in turn.citation_descriptors)
    )
    source_message_ids = tuple(
        turn.user_message_id for turn in selected if turn.user_message_id is not None
    )
    prior_context = " ".join([*(turn.question for turn in selected), *descriptors]).strip()
    if not prior_context or not is_employment_query(understand_query(prior_context)):
        return base

    sanitized_question, question_redactions = redact_retrieval_text(question)
    sanitized_context, context_redactions = redact_retrieval_text(prior_context)
    bounded_question = _truncate_head_at_word(sanitized_question, max_chars)
    context_budget = max(0, max_chars - len(bounded_question) - 1)
    bounded_context = _truncate_tail_at_word(sanitized_context, context_budget)
    if not bounded_context:
        return base

    return MemoryContext(
        original_question=question,
        retrieval_query=f"{bounded_context}\n{bounded_question}".strip(),
        used=True,
        source_turns=len(selected),
        activation_reason=reason,
        citation_context=descriptors,
        question_language=question_language,
        context_topics=topics,
        context_document_ids=document_ids,
        context_articles=articles,
        source_message_ids=source_message_ids,
        redaction_count=question_redactions + context_redactions,
    )


def build_history_turns(
    messages: list[dict[str, Any]],
    max_turns: int = 2,
) -> tuple[HistoryTurn, ...]:
    """Collect the most recent answered turns for the LLM prompt.

    Only turns with a completed, cited answer and a passing input guardrail
    are eligible — the same bar as retrieval memory — so refusals and failed
    turns never become model context. PII is redacted before returning.
    """
    turns: list[HistoryTurn] = []
    pending_question: str | None = None
    for message in messages:
        role = message.get("role")
        if role == "user":
            candidate = str(message.get("content") or "").strip()
            pending_question = candidate or None
            continue
        if role != "assistant" or pending_question is None:
            continue
        question, pending_question = pending_question, None
        if not _answer_citations(message):
            continue
        if not _guardrail_allowed(message):
            continue
        answer = str(message.get("content") or "").strip()
        if not answer:
            continue
        redacted_question, question_redactions = redact_retrieval_text(question)
        redacted_answer, answer_redactions = redact_retrieval_text(answer)
        if question_redactions or answer_redactions:
            continue
        turns.append(HistoryTurn(question=redacted_question, answer=redacted_answer))
    return tuple(turns[-max(1, max_turns) :])
