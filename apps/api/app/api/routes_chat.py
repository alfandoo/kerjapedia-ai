from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import random
import re
import threading
import time
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, DbSession, OptionalUser
from app.api.schemas import (
    AskRequest,
    AskResponse,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdateRequest,
    MessageResponse,
    PersonalizedModeUpdateRequest,
)
from app.api.state import UserRecord, now_utc
from app.api.utils import storage_root
from app.core.config import settings
from app.db.session import create_session
from app.models.business import Conversation, Message, RagRequestObservation, WorkProfile
from app.services.answering.conversation_summary import append_summary
from app.services.answering.guardrails import (
    apply_output_guardrail,
    build_guardrail_refusal,
    evaluate_input_guardrail,
)
from app.services.answering.memory_hardening import (
    MemoryContext,
    build_history_turns,
    build_memory_context,
)
from app.services.answering.openrouter_generator import ProcessingQuotaExhausted
from app.services.answering.personalized_context import (
    PersonalizedContext,
    build_personalized_context,
)
from app.services.answering.provider_cancellation import (
    ProviderCancelled,
    ProviderRequestScope,
    current_provider_scope,
)
from app.services.idempotency import IdempotencyStore, valid_idempotency_key
from app.services.providers import answer_generator_from_settings
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.governance import load_retrieval_governance
from app.services.retrieval.store import load_artifact_documents_snapshot
from app.services.telemetry import (
    drain_stage_accumulator,
    observe_rag_completion,
    observe_request_latency,
    observe_stage,
    record_outcome,
    record_provider_error,
    record_ragas_eval,
    record_ragas_faithfulness,
    record_user_behavior,
    reset_stage_accumulator,
    trace_stage,
)
from app.services.token_quota import (
    QuotaExceeded,
    mark_provider_started,
    reserve,
    reset_at,
    settle,
    snapshot,
    transfer_conversation,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("kerjapedia.rag")
_PENDING_TURN_TTL = timedelta(minutes=5)
_HEARTBEAT_SECONDS = 15.0

idempotency_store = IdempotencyStore(redis_url=settings.redis_url)


def _idempotency_request_fingerprint(payload: AskRequest) -> dict:
    return {
        "question": payload.question,
        "conversation_id": payload.conversation_id,
        "top_k": payload.top_k,
        "reasoning_mode": payload.reasoning_mode,
        "personalized_mode": payload.personalized_mode,
    }


def _resolve_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = valid_idempotency_key(raw.strip())
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_idempotency_key",
                "message": "Idempotency-Key must be 8-64 chars of letters, digits, _ or -.",
            },
        )
    return key


@dataclass(frozen=True)
class _PendingTurn:
    user_message_id: str
    previous_messages: list[dict]


def _anonymous_user(guest_id: str | None = None) -> UserRecord:
    if not guest_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-KerjaPedia-Guest-ID is required for unauthenticated chat.",
        )
    try:
        normalized_guest_id = str(UUID(guest_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-KerjaPedia-Guest-ID must be a valid UUID.",
        ) from exc
    return UserRecord(
        user_id=f"guest:{normalized_guest_id}",
        email=f"{normalized_guest_id}@guest.local",
        name="Tamu",
        roles=["guest"],
    )


def _sanitize_title(question: str) -> str:
    """Conversation titles are user input rendered in UI: collapse
    whitespace (including newlines) and strip other controls."""
    collapsed = re.sub(r"\s+", " ", question)
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", collapsed).strip()
    return cleaned[:80] or "Percakapan"


def _get_or_create_conversation(
    payload: AskRequest,
    user: UserRecord,
    session: Session,
) -> Conversation:
    if payload.conversation_id:
        conversation = session.get(Conversation, payload.conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation was not found.",
            )
        if conversation.user_id and conversation.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Conversation belongs to another user.",
            )
        guest_id = (
            user.user_id.removeprefix("guest:") if user.user_id.startswith("guest:") else None
        )
        if not conversation.user_id and conversation.guest_id:
            if guest_id != conversation.guest_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Conversation belongs to another user.",
                )
        elif not conversation.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Legacy unowned conversations cannot be accessed.",
            )
        return conversation

    conversation_id = f"conv_{uuid4().hex}"
    title = _sanitize_title(payload.question)
    user_id = user.user_id if user.roles != ["guest"] else None
    guest_id = user.user_id.removeprefix("guest:") if user.user_id.startswith("guest:") else None
    conversation = Conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        guest_id=guest_id,
        title=title,
        personalized_mode=bool(payload.personalized_mode and user_id),
    )
    session.add(conversation)
    session.commit()
    return conversation


def _get_owned_conversation(
    conversation_id: str,
    user: UserRecord,
    session: Session,
) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation was not found.",
        )
    if conversation.user_id and conversation.user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation belongs to another user.",
        )
    guest_id = user.user_id.removeprefix("guest:") if user.user_id.startswith("guest:") else None
    if not conversation.user_id and conversation.guest_id:
        if guest_id != conversation.guest_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Conversation belongs to another user.",
            )
    elif not conversation.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy unowned conversations cannot be accessed.",
        )
    return conversation


def _conversation_summary(
    conversation: Conversation, session: Session | None = None
) -> ConversationSummary:
    message_count = 0
    if session is not None:
        message_count = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.conversation_id)
            .count()
        )
    return ConversationSummary(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=message_count,
        personalized_mode=conversation.personalized_mode,
    )


def _recent_messages(
    conversation: Conversation,
    session: Session,
    limit: int = 8,
) -> list[dict]:
    rows = (
        session.query(Message)
        .filter(Message.conversation_id == conversation.conversation_id)
        .order_by(Message.sequence_no.desc(), Message.message_id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "role": row.role,
            "content": row.content,
            "metadata": row.meta_data or {},
            "message_id": row.message_id,
            "sequence_no": row.sequence_no,
        }
        for row in reversed(rows)
    ]


def _personalized_context(
    conversation: Conversation, user: UserRecord, question: str, session: Session
) -> PersonalizedContext | None:
    if not conversation.personalized_mode or not conversation.user_id:
        return None
    if conversation.user_id != user.user_id:
        return None
    row = session.get(WorkProfile, user.user_id)
    if row is None:
        return build_personalized_context(question, {})
    return build_personalized_context(
        question,
        {
            "province": row.province,
            "employment_status": row.employment_status,
            "start_date": row.start_date.date().isoformat() if row.start_date else None,
            "monthly_wage": row.monthly_wage,
        },
    )


def _apply_personalized_retrieval(
    memory: MemoryContext, context: PersonalizedContext | None
) -> MemoryContext:
    if context is None or not context.retrieval_hint:
        return memory
    return replace(
        memory,
        retrieval_query=f"{memory.retrieval_query} {context.retrieval_hint}".strip(),
    )


def _retrieve(memory: MemoryContext, top_k: int, session: Session):
    governance = load_retrieval_governance(
        session,
        allow_unpublished=settings.rag_allow_unpublished,
    )
    # Release the read transaction before calling external retrieval providers.
    session.rollback()
    if settings.vector_store not in ("upstash_vector", "artifact"):
        raise RuntimeError(
            f"Unsupported VECTOR_STORE: {settings.vector_store!r}. "
            "Supported stores: upstash_vector, artifact."
        )
    from app.services.providers import upstash_vector_store_from_settings

    if settings.vector_store == "upstash_vector":
        retrieval = upstash_vector_store_from_settings(
            settings,
            relationship_index=governance.relationship_index,
            allow_unpublished=settings.rag_allow_unpublished,
        ).search(
            memory.original_question,
            top_k=top_k,
            min_final_score=governance.min_final_score,
            retrieval_query=memory.retrieval_query,
            context_topics=memory.context_topics,
            context_document_ids=memory.context_document_ids,
            context_articles=memory.context_articles,
        )
        return replace(
            retrieval,
            index_release_id=governance.active_release_id,
            index_namespace=settings.upstash_vector_namespace,
        )
    eligible_versions = tuple(sorted(governance.eligible_versions.items()))
    if settings.rag_allow_unpublished and not eligible_versions:
        eligible_versions = None
    eligible_builds = tuple(sorted(governance.eligible_builds.items())) or None
    documents = load_artifact_documents_snapshot(
        storage_root(),
        eligible_versions,
        eligible_builds,
    )
    retrieval = RetrievalEngine(
        documents=list(documents),
        min_final_score=governance.min_final_score,
        top_k=top_k,
        relationship_index=governance.relationship_index,
        diversity_lambda=settings.retrieval_diversity_lambda,
    ).search(
        memory.original_question,
        top_k=top_k,
        retrieval_query=memory.retrieval_query,
        context_topics=memory.context_topics,
        context_document_ids=memory.context_document_ids,
        context_articles=memory.context_articles,
    )
    return replace(
        retrieval,
        index_release_id=governance.active_release_id,
        index_namespace=governance.active_namespace,
    )


def _rerank_personalized(retrieval, context: PersonalizedContext | None, top_k: int):
    if (
        context is None
        or not context.facts.get("province")
        or str(context.facts["province"]) not in context.retrieval_hint
        or not retrieval.results
    ):
        return retrieval
    province = str(context.facts["province"]).casefold()

    def score(item):
        metadata = item.document.metadata
        location = " ".join(
            str(metadata.get(key) or "")
            for key in ("province", "jurisdiction", "region", "title", "short_title")
        ).casefold()
        return item.final_score + (0.02 if province in location else 0)

    return replace(retrieval, results=sorted(retrieval.results, key=score, reverse=True)[:top_k])


def _retrieve_with_isolated_session(
    memory: MemoryContext,
    top_k: int,
    personalized_context: PersonalizedContext | None = None,
):
    """Run threaded retrieval without sharing the request SQLAlchemy session."""
    with create_session() as isolated_session:
        pool_size = min(8, top_k + 3) if personalized_context else top_k
        retrieval = _retrieve(memory, pool_size, isolated_session)
        return _rerank_personalized(retrieval, personalized_context, top_k)


def _generate_with_fresh_generator(
    question: str,
    retrieval,
    history,
    reasoning_mode: str,
    output_cap: int,
    reserved_tokens: int,
    personalized_context: PersonalizedContext | None = None,
):
    """Run blocking LLM generation in a worker thread (fresh instance)."""
    generator = copy.copy(
        answer_generator_from_settings(
            settings,
            reasoning_mode=reasoning_mode,
        )
    )
    if hasattr(generator, "max_tokens"):
        generator.max_tokens = min(generator.max_tokens, output_cap)
        generator.token_budget = reserved_tokens
    generator.personalized_context = (
        personalized_context.prompt_block if personalized_context else ""
    )
    return generator.generate(question, retrieval, history=history)


# Per-stage budgets keep the non-streaming answer path under the 150s
# request-timeout middleware with headroom for turn bookkeeping and
# observability writes (60 + 80 = 140). Separate budgets let latency
# histograms and provider-error counters tell Upstash slowness apart from
# Groq slowness instead of one opaque "request too long".
_RETRIEVAL_TIMEOUT_SECONDS = 60.0
_GENERATION_TIMEOUT_SECONDS = {
    "fast": 45.0,
    "standard": 65.0,
    "deep": 80.0,
}


def _next_message_sequence(conversation_id: str, session: Session) -> int:
    current = session.execute(
        select(func.coalesce(func.max(Message.sequence_no), 0)).where(
            Message.conversation_id == conversation_id
        )
    ).scalar_one()
    return int(current) + 1


def _begin_turn(
    conversation: Conversation,
    payload: AskRequest,
    session: Session,
) -> _PendingTurn:
    locked_conversation = session.execute(
        select(Conversation)
        .where(Conversation.conversation_id == conversation.conversation_id)
        .with_for_update()
    ).scalar_one()
    previous_messages = _recent_messages(locked_conversation, session)
    latest = (
        session.query(Message)
        .filter(Message.conversation_id == locked_conversation.conversation_id)
        .order_by(Message.sequence_no.desc(), Message.message_id.desc())
        .first()
    )
    if latest and (latest.meta_data or {}).get("turn_status") == "processing":
        created_at = latest.created_at or now_utc()
        if now_utc() - created_at < _PENDING_TURN_TTL:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "conversation_turn_in_progress",
                    "message": "Another turn is still being processed for this conversation.",
                },
            )
        latest.meta_data = {
            **(latest.meta_data or {}),
            "turn_status": "abandoned",
            "memory_eligible": False,
        }

    user_message_id = f"msg_{uuid4().hex}"
    session.add(
        Message(
            message_id=user_message_id,
            conversation_id=locked_conversation.conversation_id,
            sequence_no=_next_message_sequence(
                locked_conversation.conversation_id,
                session,
            ),
            role="user",
            content=payload.question,
            meta_data={
                "turn_status": "processing",
                "memory_eligible": False,
            },
        )
    )
    locked_conversation.updated_at = now_utc()
    session.commit()
    return _PendingTurn(
        user_message_id=user_message_id,
        previous_messages=previous_messages,
    )


def _mark_turn_failed(
    user_message_id: str,
    session: Session,
    failure_code: str,
) -> None:
    try:
        session.rollback()
        user_message = session.get(Message, user_message_id)
        if user_message is None:
            session.rollback()
            return
        if (user_message.meta_data or {}).get("turn_status") != "processing":
            session.rollback()
            return
        user_message.meta_data = {
            **(user_message.meta_data or {}),
            "turn_status": "cancelled" if failure_code == "stream_cancelled" else "failed",
            "memory_eligible": False,
            "failure_code": failure_code,
        }
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("chat_turn_failure_state_not_persisted message_id=%s", user_message_id)


def _usage_key(conversation: Conversation) -> str:
    if conversation.user_id:
        return conversation.user_id
    if conversation.guest_id:
        return f"guest:{conversation.guest_id}"
    return "unknown"


def _quota_http_error(exc: QuotaExceeded) -> HTTPException:
    retry_after = max(1, math.ceil((exc.reset_at - now_utc()).total_seconds()))
    return HTTPException(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        detail={
            "code": "daily_token_quota_exceeded",
            "message": "Batas token harian habis. Coba lagi setelah reset.",
            "reset_at": exc.reset_at.isoformat(),
        },
    )


def _reserve_turn(
    conversation: Conversation, pending_turn: _PendingTurn, payload: AskRequest, session: Session
):
    try:
        return reserve(
            identity_key=_usage_key(conversation),
            conversation_id=conversation.conversation_id,
            turn_id=pending_turn.user_message_id,
            question=payload.question,
            previous_messages=pending_turn.previous_messages,
        )
    except QuotaExceeded as exc:
        _mark_turn_failed(pending_turn.user_message_id, session, "daily_token_quota_exceeded")
        raise _quota_http_error(exc) from exc
    except Exception as exc:
        _mark_turn_failed(pending_turn.user_message_id, session, "usage_metering_unavailable")
        logger.exception("usage_reservation_failed")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "usage_metering_unavailable",
                "message": "Pencatatan penggunaan sementara tidak tersedia.",
            },
        ) from exc


def _store_answer(
    conversation: Conversation,
    user_message_id: str,
    answer,
    best_score,
    rag_trace: dict | None = None,
    session: Session | None = None,
) -> None:
    if session is None:
        return
    now = now_utc()
    session.execute(
        select(Conversation)
        .where(Conversation.conversation_id == conversation.conversation_id)
        .with_for_update()
    ).scalar_one()
    user_msg = session.get(Message, user_message_id)
    if user_msg is None:
        raise RuntimeError("The pending chat turn no longer exists.")
    latest_message_id = session.execute(
        select(Message.message_id)
        .where(Message.conversation_id == conversation.conversation_id)
        .order_by(Message.sequence_no.desc(), Message.message_id.desc())
        .limit(1)
    ).scalar_one()
    if (user_msg.meta_data or {}).get(
        "turn_status"
    ) != "processing" or latest_message_id != user_message_id:
        raise RuntimeError("The pending chat turn is no longer active.")
    memory_eligible = bool(
        (rag_trace or {}).get("guardrail", {}).get("allowed", True)
        and answer.answer_status == "answered"
        and answer.refusal_reason is None
        and answer.citations
    )
    user_msg.meta_data = {
        "rag_trace": rag_trace or {},
        "memory_eligible": memory_eligible,
        "turn_status": "completed",
        "answer_status": answer.answer_status,
        "has_valid_citations": bool(answer.citations),
    }

    asst_msg = Message(
        message_id=f"msg_{uuid4().hex}",
        conversation_id=conversation.conversation_id,
        sequence_no=_next_message_sequence(conversation.conversation_id, session),
        role="assistant",
        content=answer.answer,
        meta_data={
            "answer": _public_answer_payload(answer),
            "retrieval_score": best_score,
            "token_usage": answer.debug.get(
                "token_usage",
                {"prompt_tokens": 0, "completion_tokens": 0},
            ),
            "rag_trace": rag_trace or {},
        },
    )
    session.add(asst_msg)
    if memory_eligible:
        conversation.memory_summary = append_summary(
            conversation.memory_summary,
            user_msg.content,
            user_message_id,
            [asdict(citation) for citation in answer.citations],
        )
    settle(user_message_id, answer.debug.get("token_usage", {}), answer.answer)
    conversation.updated_at = now
    session.commit()


def _public_answer_payload(answer) -> dict:
    payload = asdict(answer)
    payload["debug"] = {
        "trace_id": answer.trace_id,
        "prompt_version_id": answer.prompt_version_id,
    }
    return payload


def _public_message_metadata(metadata: dict | None) -> dict:
    raw = metadata or {}
    return {
        key: value
        for key, value in raw.items()
        if key
        not in {
            "rag_trace",
            "memory_eligible",
            "turn_status",
            "answer_status",
            "has_valid_citations",
            "failure_code",
            "system_prompt",
            "rendered_user_prompt",
        }
    }


def _stream_event(event: str, **payload) -> bytes:
    serialized = json.dumps(
        {"event": event, **payload},
        ensure_ascii=False,
        default=str,
    )
    return f"{serialized}\n".encode()


async def _pings_while(
    task: asyncio.Task,
    timeout_seconds: float | None = None,
    request: Request | None = None,
    cancellation_scope: ProviderRequestScope | None = None,
):
    """Yield keepalive pings until the awaited stage finishes.

    Proxies and load balancers drop idle SSE streams; a ping every
    heartbeat interval keeps the connection (and the UI spinner) alive.
    Unknown events are ignored by the web client. When `timeout_seconds`
    is set, a hung stage raises TimeoutError instead of pinging forever
    (the stream path is exempt from the 150s request-timeout middleware).
    """
    started_at = time.perf_counter()
    next_ping_at = started_at + _HEARTBEAT_SECONDS
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.5)
            if task in done:
                break
            if request is not None and await request.is_disconnected():
                if cancellation_scope is not None:
                    cancellation_scope.cancel()
                raise ProviderCancelled()
            now = time.perf_counter()
            if timeout_seconds is not None and now - started_at > timeout_seconds:
                raise TimeoutError(f"Stage exceeded {timeout_seconds:.0f}s budget.")
            if now >= next_ping_at:
                yield _stream_event("ping")
                next_ping_at = now + _HEARTBEAT_SECONDS
    finally:
        if not task.done():
            if cancellation_scope is not None:
                cancellation_scope.cancel()
            task.cancel()


def _server_rag_trace(guardrail, memory, retrieval, answer, reasoning_mode: str) -> dict:
    retrieval_items = retrieval.results if retrieval else []
    return {
        "reasoning_mode": reasoning_mode,
        "guardrail": {"allowed": guardrail.allowed, "reason": guardrail.reason},
        "memory": {
            "used": memory.used,
            "source_turns": memory.source_turns,
            "citation_context_count": len(memory.citation_context),
            "retrieval_query_sha256": hashlib.sha256(memory.retrieval_query.encode()).hexdigest(),
            "activation_reason": memory.activation_reason,
            "question_language": memory.question_language,
            "context_topics": list(memory.context_topics),
            "context_document_count": len(memory.context_document_ids),
            "context_article_count": len(memory.context_articles),
            "redaction_count": memory.redaction_count,
        },
        "pipeline": {
            "vector_store": settings.vector_store,
            "embedding_model": (
                "upstash-hosted:text-embedding-3-small"
                if settings.vector_store == "upstash_vector"
                else "local-hash-embedding-v1"
            ),
            "generator_model": (
                settings.groq_model
                if settings.llm_provider == "groq"
                else (
                    settings.openrouter_model if settings.llm_provider == "openrouter" else "local"
                )
            ),
            "verifier_model": settings.claim_verifier_model,
            "reranker_model": "heuristic",
            "prompt_version": answer.prompt_version_id,
            "answer_version": answer.answer_version,
            "index_release_id": retrieval.index_release_id if retrieval else None,
            "index_namespace": retrieval.index_namespace if retrieval else None,
            "question_language": memory.question_language,
        },
        "retrieval": [
            {
                "chunk_id": item.document.chunk_id,
                "document_id": item.document.document_id,
                "document_version": item.document.document_version,
                "final_score": item.final_score,
            }
            for item in retrieval_items[:8]
        ],
        "timing": retrieval.timing if retrieval else {},
        "context_metrics": retrieval.context_metrics if retrieval else {},
        "verification": [
            {
                "cited_chunk_ids": claim.cited_chunk_ids,
                "supported": claim.supported,
                "support_score": claim.support_score,
                "support_detail": claim.support_detail,
            }
            for claim in answer.claims
        ],
        "generation": {
            "failure_category": answer.debug.get("failure_category"),
            "provider_failure_type": answer.debug.get("provider_failure_type"),
            "generation_attempts": answer.debug.get("generation_attempts"),
            "validation_issues": answer.debug.get("validation_issues", []),
        },
        "token_usage": answer.debug.get("token_usage", {}),
    }


_RAGAS_CONTEXT_CHUNKS = 8
_RAGAS_CONTEXT_CHARS = 1500


def _ragas_contexts(retrieval) -> list[str]:
    if retrieval is None:
        return []
    contexts: list[str] = []
    for item in (retrieval.results or [])[:_RAGAS_CONTEXT_CHUNKS]:
        text = (getattr(item.document, "text", "") or "").strip()
        if text:
            contexts.append(text[:_RAGAS_CONTEXT_CHARS])
    return contexts


def _run_ragas_online_eval(question: str, answer_text: str, contexts: list[str]) -> None:
    try:
        from app.services.evaluation.ragas_metrics import (
            build_ragas_faithfulness,
            score_ragas_faithfulness,
        )

        scorer = build_ragas_faithfulness(settings)
        score = score_ragas_faithfulness(
            scorer,
            question=question,
            response=answer_text,
            contexts=contexts,
        )
        record_ragas_faithfulness(score)
        record_ragas_eval("success", score)
    except Exception:
        record_ragas_eval("failed")
        logger.exception("ragas_online_eval_failed")


def _maybe_sample_ragas_online(question: str, answer, retrieval) -> None:
    if not settings.ragas_enabled:
        return
    try:
        rate = float(settings.ragas_sample_rate)
    except (TypeError, ValueError):
        return
    if rate <= 0 or random.random() >= min(rate, 1.0):
        return
    if getattr(answer, "answer_status", None) != "answered":
        return
    answer_text = (getattr(answer, "answer", "") or "").strip()
    if not answer_text:
        return
    contexts = _ragas_contexts(retrieval)
    if not contexts:
        return
    thread = threading.Thread(
        target=_run_ragas_online_eval,
        args=(question, answer_text, contexts),
        daemon=True,
    )
    thread.start()


def _observe_request_completion(
    question: str,
    memory,
    answer,
    retrieval,
    latency_ms: int,
    *,
    turn_id: str | None = None,
    reasoning_mode: str = "standard",
    first_status_ms: int | None = None,
    first_content_ms: int | None = None,
    disconnected: bool = False,
) -> None:
    try:
        topics = tuple(getattr(memory, "context_topics", ()) or ())
        topic = str(topics[0]) if topics else "unknown"
        record_user_behavior(topic, bool(getattr(memory, "used", False)))
    except Exception:
        logger.debug("observability_user_behavior_failed", exc_info=True)
    try:
        observe_request_latency(latency_ms / 1000.0)
    except Exception:
        logger.debug("observability_request_latency_failed", exc_info=True)
    try:
        _record_request_observation(
            outcome=getattr(answer, "answer_status", "unknown"),
            memory=memory,
            answer=answer,
            latency_ms=latency_ms,
            turn_id=turn_id,
            reasoning_mode=reasoning_mode,
            first_status_ms=first_status_ms,
            first_content_ms=first_content_ms,
            disconnected=disconnected,
        )
    except Exception:
        logger.debug("observability_request_row_failed", exc_info=True)
    try:
        _maybe_sample_ragas_online(question, answer, retrieval)
    except Exception:
        logger.debug("observability_ragas_sampling_failed", exc_info=True)


def _record_request_observation(
    outcome: str,
    memory=None,
    answer=None,
    latency_ms=None,
    *,
    turn_id: str | None = None,
    reasoning_mode: str = "standard",
    first_status_ms: int | None = None,
    first_content_ms: int | None = None,
    disconnected: bool = False,
    usage_override: dict | None = None,
    provider_failure_override: bool = False,
) -> None:
    """Durable per-turn metrics row; isolated session so it never poisons chat."""
    try:
        topics = tuple(getattr(memory, "context_topics", ()) or ()) if memory else ()
        debug = getattr(answer, "debug", {}) or {}
        usage = usage_override or debug.get(
            "token_usage", {"prompt_tokens": 0, "completion_tokens": 0}
        )
        claims = getattr(answer, "claims", []) or []
        stages = drain_stage_accumulator()
        with create_session() as observation_session:
            observation_session.add(
                RagRequestObservation(
                    outcome=str(outcome or "unknown")[:40],
                    turn_id=turn_id,
                    reasoning_mode=(
                        reasoning_mode
                        if reasoning_mode in {"fast", "standard", "deep"}
                        else "standard"
                    ),
                    time_to_first_status_ms=first_status_ms,
                    time_to_first_content_ms=first_content_ms,
                    disconnected=disconnected,
                    retry_count=max(0, int(debug.get("transient_retries", 0) or 0)),
                    provider_failure=(
                        provider_failure_override or bool(debug.get("provider_failure_type"))
                    ),
                    request_latency_ms=float(latency_ms) if latency_ms is not None else None,
                    prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
                    completion_tokens=int(usage.get("completion_tokens", 0) or 0),
                    llm_model=str((getattr(answer, "debug", {}) or {}).get("llm_model", "non_llm"))[
                        :160
                    ],
                    claims_supported=sum(1 for claim in claims if claim.supported),
                    claims_unsupported=sum(1 for claim in claims if not claim.supported),
                    topic=str(topics[0]) if topics else "unknown",
                    is_followup=bool(getattr(memory, "used", False)) if memory else False,
                    stage_latencies=[
                        {
                            "stage": str(entry.get("stage")),
                            "provider": str(entry.get("provider")),
                            "seconds": float(entry.get("seconds", 0) or 0),
                        }
                        for entry in stages
                    ],
                )
            )
            observation_session.commit()
    except Exception:
        logger.debug("observability_request_row_failed", exc_info=True)


def _log_rag_completion(answer, latency_ms: int) -> None:
    logger.info(
        "rag_completed trace_id=%s status=%s latency_ms=%s citations=%s "
        "prompt_version=%s answer_version=%s reasoning_mode=%s",
        answer.trace_id,
        answer.answer_status,
        latency_ms,
        len(answer.citations),
        answer.prompt_version_id,
        answer.answer_version,
        answer.debug.get("reasoning_mode", "standard"),
    )


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    payload: AskRequest,
    response: Response,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AskResponse:
    started_at = time.perf_counter()
    trace_id = f"rag_{uuid4().hex}"
    active_user = user or _anonymous_user(guest_id)
    idempotency_key = _resolve_idempotency_key(idempotency_key)
    fingerprint = _idempotency_request_fingerprint(payload)
    if idempotency_key is not None:
        replayed = idempotency_store.recall(active_user.user_id, idempotency_key)
        if replayed is not None and replayed.get("request") == fingerprint:
            response.headers["X-Idempotent-Replayed"] = "true"
            stored = replayed["response"]
            return AskResponse(
                conversation_id=stored["conversation_id"],
                answer=stored["answer"],
                latency_ms=stored["latency_ms"],
                retrieval_score=stored.get("retrieval_score"),
                token_usage=stored.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0}),
                reasoning_mode=stored.get("reasoning_mode", payload.reasoning_mode),
            )
        if replayed is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "idempotency_key_reuse",
                    "message": "Idempotency-Key was already used with a different request.",
                },
            )
    conversation = _get_or_create_conversation(payload, active_user, session)
    personalized_context = _personalized_context(
        conversation, active_user, payload.question, session
    )
    pending_turn = _begin_turn(conversation, payload, session)
    reservation = _reserve_turn(conversation, pending_turn, payload, session)
    reset_stage_accumulator()

    try:
        guardrail = evaluate_input_guardrail(payload.question)
        memory = _apply_personalized_retrieval(
            build_memory_context(
                payload.question,
                pending_turn.previous_messages,
                summary=conversation.memory_summary,
            ),
            personalized_context,
        )
        if not guardrail.allowed:
            answer = build_guardrail_refusal(
                payload.question,
                guardrail.reason or "input_guardrail_blocked",
            )
            retrieval = None
        else:
            history = build_history_turns(
                pending_turn.previous_messages, summary=conversation.memory_summary
            )
            retrieval_started = time.perf_counter()
            try:
                from app.services.monitoring.tracing import end_span as _end_span
                from app.services.monitoring.tracing import start_span as _start_span

                with trace_stage("retrieval", settings.vector_store):
                    _start_span("retrieval", settings.vector_store)
                    try:
                        retrieval = await asyncio.wait_for(
                            asyncio.to_thread(
                                _retrieve_with_isolated_session,
                                memory,
                                payload.top_k,
                                personalized_context,
                            ),
                            timeout=_RETRIEVAL_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        _end_span("error", f"{type(exc).__name__}")
                        raise
                    _end_span("ok")
            except TimeoutError as exc:
                elapsed = time.perf_counter() - retrieval_started
                observe_stage("retrieval", settings.vector_store, elapsed)
                record_outcome("timeout_retrieval")
                record_provider_error("retrieval", settings.vector_store)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={
                        "code": "request_timeout",
                        "message": "The request took too long to complete.",
                        "stage": "retrieval",
                        "trace_id": trace_id,
                    },
                ) from exc
            observe_stage(
                "retrieval",
                settings.vector_store,
                time.perf_counter() - retrieval_started,
            )
            mark_provider_started(pending_turn.user_message_id)
            generation_started = time.perf_counter()
            try:
                with trace_stage("generation_and_verification", settings.llm_provider):
                    _start_span("generation", settings.llm_provider)
                    try:
                        answer = await asyncio.wait_for(
                            asyncio.to_thread(
                                _generate_with_fresh_generator,
                                payload.question,
                                retrieval,
                                history,
                                payload.reasoning_mode,
                                reservation.output_cap,
                                reservation.reserved_tokens,
                                personalized_context,
                            ),
                            timeout=_GENERATION_TIMEOUT_SECONDS[payload.reasoning_mode],
                        )
                    except Exception as exc:
                        _end_span("error", f"{type(exc).__name__}")
                        raise
                    _end_span("ok")
            except TimeoutError as exc:
                elapsed = time.perf_counter() - generation_started
                observe_stage("generation_and_verification", settings.llm_provider, elapsed)
                record_outcome("timeout_generation")
                record_provider_error("generation_and_verification", settings.llm_provider)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={
                        "code": "request_timeout",
                        "message": "The request took too long to complete.",
                        "stage": "generation_and_verification",
                        "trace_id": trace_id,
                    },
                ) from exc
            observe_stage(
                "generation_and_verification",
                settings.llm_provider,
                time.perf_counter() - generation_started,
            )
        best_score = retrieval.results[0].final_score if retrieval and retrieval.results else None
        answer, output_warnings = apply_output_guardrail(answer)
        if output_warnings:
            answer = replace(answer, warnings=[*answer.warnings, *output_warnings])
        rag_trace = _server_rag_trace(guardrail, memory, retrieval, answer, payload.reasoning_mode)
        answer.debug.update(rag_trace)
        answer = replace(answer, trace_id=trace_id)
        _store_answer(
            conversation,
            pending_turn.user_message_id,
            answer,
            best_score,
            rag_trace,
            session,
        )
    except ProcessingQuotaExhausted as exc:
        settle(pending_turn.user_message_id)
        _mark_turn_failed(pending_turn.user_message_id, session, "daily_token_quota_exceeded")
        raise _quota_http_error(QuotaExceeded(reset_at())) from exc
    except HTTPException:
        try:
            settle(pending_turn.user_message_id)
        except Exception:
            logger.exception("usage_settlement_failed")
        _mark_turn_failed(
            pending_turn.user_message_id,
            session,
            "rag_pipeline_failed",
        )
        record_outcome("failed")
        _record_request_observation(
            "failed",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            turn_id=pending_turn.user_message_id,
            reasoning_mode=payload.reasoning_mode,
            provider_failure_override=True,
        )
        raise
    except Exception as exc:
        try:
            settle(pending_turn.user_message_id)
        except Exception:
            logger.exception("usage_settlement_failed")
        _mark_turn_failed(
            pending_turn.user_message_id,
            session,
            "rag_pipeline_failed",
        )
        record_outcome("failed")
        record_provider_error("rag_pipeline", f"{settings.vector_store}+{settings.llm_provider}")
        _record_request_observation(
            "failed",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            turn_id=pending_turn.user_message_id,
            reasoning_mode=payload.reasoning_mode,
            provider_failure_override=True,
        )
        logger.exception("rag_failed trace_id=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "rag_temporarily_unavailable",
                "message": "The grounded answer service is temporarily unavailable.",
                "trace_id": trace_id,
            },
        ) from exc
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    record_outcome(answer.answer_status)
    observe_rag_completion(answer, retrieval)
    _observe_request_completion(
        payload.question,
        memory,
        answer,
        retrieval,
        latency_ms,
        turn_id=pending_turn.user_message_id,
        reasoning_mode=payload.reasoning_mode,
        first_content_ms=latency_ms,
    )
    _log_rag_completion(answer, latency_ms)
    completed = AskResponse(
        conversation_id=conversation.conversation_id,
        answer=_public_answer_payload(answer),
        latency_ms=latency_ms,
        retrieval_score=best_score,
        token_usage=answer.debug.get(
            "token_usage",
            {"prompt_tokens": 0, "completion_tokens": 0},
        ),
        reasoning_mode=payload.reasoning_mode,
    )
    transient = completed.answer.get("answer_status") == "temporarily_unavailable"
    if idempotency_key is not None and not transient:
        idempotency_store.remember(
            active_user.user_id,
            idempotency_key,
            {
                "request": fingerprint,
                "response": {
                    "conversation_id": completed.conversation_id,
                    "answer": completed.answer,
                    "latency_ms": completed.latency_ms,
                    "retrieval_score": completed.retrieval_score,
                    "token_usage": completed.token_usage,
                    "reasoning_mode": completed.reasoning_mode,
                },
            },
        )
    return completed


@router.post("/ask/stream")
def ask_question_stream(
    payload: AskRequest,
    request: Request,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    active_user = user or _anonymous_user(guest_id)
    idempotency_key = _resolve_idempotency_key(idempotency_key)
    fingerprint = _idempotency_request_fingerprint(payload)
    replayed = (
        idempotency_store.recall(active_user.user_id, idempotency_key)
        if idempotency_key is not None
        else None
    )
    if replayed is not None and replayed.get("request") != fingerprint:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "idempotency_key_reuse",
                "message": "Idempotency-Key was already used with a different request.",
            },
        )
    if replayed is not None:
        stored = replayed["response"]

        async def replay_stream():
            yield _stream_event("start", conversation_id=stored["conversation_id"], status="OK")
            yield _stream_event("done", response=stored)

        return StreamingResponse(
            replay_stream(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Idempotent-Replayed": "true",
            },
        )
    conversation = _get_or_create_conversation(payload, active_user, session)
    personalized_context = _personalized_context(
        conversation, active_user, payload.question, session
    )
    pending_turn = _begin_turn(conversation, payload, session)
    reservation = _reserve_turn(conversation, pending_turn, payload, session)
    trace_id = f"rag_{uuid4().hex}"

    async def event_stream():
        # Reset here (not in the handler above): the generator below may run
        # in a different task than the handler, and the stage accumulator is
        # task-local. Observe/drain calls below must share this task's context.
        reset_stage_accumulator()
        started_at = time.perf_counter()
        stored = False
        failure_code = "stream_cancelled"
        cancellation_scope: ProviderRequestScope | None = None
        first_status_ms = int((time.perf_counter() - started_at) * 1000)
        first_content_ms: int | None = None
        try:
            yield _stream_event(
                "start",
                conversation_id=conversation.conversation_id,
                status="Menganalisis pertanyaan",
                reasoning_mode=payload.reasoning_mode,
            )
            guardrail = evaluate_input_guardrail(payload.question)
            memory = _apply_personalized_retrieval(
                build_memory_context(
                    payload.question,
                    pending_turn.previous_messages,
                    summary=conversation.memory_summary,
                ),
                personalized_context,
            )
            if not guardrail.allowed:
                yield _stream_event("thinking", status="Memeriksa keamanan permintaan")
                answer = build_guardrail_refusal(
                    payload.question,
                    guardrail.reason or "input_guardrail_blocked",
                )
                retrieval = None
            else:
                yield _stream_event("thinking", status="Menelusuri regulasi resmi")
                retrieval_started = time.perf_counter()
                try:
                    from app.services.monitoring.tracing import end_span as _end_span
                    from app.services.monitoring.tracing import (
                        start_span as _start_span,
                    )

                    with trace_stage("retrieval", settings.vector_store):
                        _start_span("retrieval", settings.vector_store)
                        retrieval_task = asyncio.ensure_future(
                            asyncio.to_thread(
                                _retrieve_with_isolated_session,
                                memory,
                                payload.top_k,
                                personalized_context,
                            )
                        )
                        try:
                            async for ping in _pings_while(
                                retrieval_task,
                                timeout_seconds=_RETRIEVAL_TIMEOUT_SECONDS,
                                request=request,
                            ):
                                yield ping
                            retrieval = retrieval_task.result()
                        except Exception as exc:
                            _end_span("error", f"{type(exc).__name__}")
                            raise
                        _end_span("ok")
                except TimeoutError:
                    observe_stage(
                        "retrieval",
                        settings.vector_store,
                        time.perf_counter() - retrieval_started,
                    )
                    record_outcome("timeout_retrieval")
                    record_provider_error("retrieval", settings.vector_store)
                    raise
                observe_stage(
                    "retrieval",
                    settings.vector_store,
                    time.perf_counter() - retrieval_started,
                )
                yield _stream_event("thinking", status="Menyusun jawaban berdasarkan sumber")
                generator = copy.copy(
                    answer_generator_from_settings(
                        settings,
                        reasoning_mode=payload.reasoning_mode,
                    )
                )
                history = build_history_turns(
                    pending_turn.previous_messages, summary=conversation.memory_summary
                )
                generator.personalized_context = (
                    personalized_context.prompt_block if personalized_context else ""
                )
                if hasattr(generator, "max_tokens"):
                    generator.max_tokens = min(generator.max_tokens, reservation.output_cap)
                    generator.token_budget = reservation.reserved_tokens
                mark_provider_started(pending_turn.user_message_id)
                cancellation_scope = ProviderRequestScope(asyncio.get_running_loop())
                generation_started = time.perf_counter()
                try:
                    with trace_stage("generation_and_verification", settings.llm_provider):
                        _start_span("generation", settings.llm_provider)
                        scope_token = current_provider_scope.set(cancellation_scope)
                        try:
                            generation_task = asyncio.ensure_future(
                                asyncio.to_thread(
                                    generator.generate,
                                    payload.question,
                                    retrieval,
                                    history=history,
                                )
                            )
                        finally:
                            current_provider_scope.reset(scope_token)
                        try:
                            async for ping in _pings_while(
                                generation_task,
                                timeout_seconds=_GENERATION_TIMEOUT_SECONDS[payload.reasoning_mode],
                                request=request,
                                cancellation_scope=cancellation_scope,
                            ):
                                yield ping
                            answer = generation_task.result()
                        except Exception as exc:
                            _end_span("error", f"{type(exc).__name__}")
                            raise
                        _end_span("ok")
                except TimeoutError:
                    observe_stage(
                        "generation_and_verification",
                        settings.llm_provider,
                        time.perf_counter() - generation_started,
                    )
                    record_outcome("timeout_generation")
                    record_provider_error("generation_and_verification", settings.llm_provider)
                    raise
                observe_stage(
                    "generation_and_verification",
                    settings.llm_provider,
                    time.perf_counter() - generation_started,
                )
            best_score = (
                retrieval.results[0].final_score if retrieval and retrieval.results else None
            )
            rag_trace = _server_rag_trace(
                guardrail, memory, retrieval, answer, payload.reasoning_mode
            )
            answer.debug.update(rag_trace)
            answer = replace(answer, trace_id=trace_id)
            guarded, output_warnings = apply_output_guardrail(answer)
            if output_warnings:
                answer = replace(guarded, warnings=[*guarded.warnings, *output_warnings])
            if await request.is_disconnected():
                raise ProviderCancelled()
            _store_answer(
                conversation,
                pending_turn.user_message_id,
                answer,
                best_score,
                rag_trace,
                session,
            )
            stored = True
        except (ProviderCancelled, asyncio.CancelledError):
            failure_code = "stream_cancelled"
            if cancellation_scope is not None:
                cancellation_scope.cancel()
            _record_request_observation(
                "cancelled",
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                turn_id=pending_turn.user_message_id,
                reasoning_mode=payload.reasoning_mode,
                first_status_ms=first_status_ms,
                disconnected=True,
                usage_override=cancellation_scope.usage if cancellation_scope else None,
            )
            return
        except GeneratorExit:
            failure_code = "stream_cancelled"
            if cancellation_scope is not None:
                cancellation_scope.cancel()
            _record_request_observation(
                "cancelled",
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                turn_id=pending_turn.user_message_id,
                reasoning_mode=payload.reasoning_mode,
                first_status_ms=first_status_ms,
                disconnected=True,
                usage_override=cancellation_scope.usage if cancellation_scope else None,
            )
            raise
        except ProcessingQuotaExhausted:
            failure_code = "daily_token_quota_exceeded"
            yield _stream_event(
                "error",
                code="daily_token_quota_exceeded",
                detail="Daily token quota was reached during processing.",
                reset_at=reset_at().isoformat(),
            )
            return
        except TimeoutError:
            failure_code = "request_timeout"
            logger.exception("rag_stage_timeout trace_id=%s", trace_id)
            _record_request_observation(
                "failed",
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                turn_id=pending_turn.user_message_id,
                reasoning_mode=payload.reasoning_mode,
                first_status_ms=first_status_ms,
                provider_failure_override=True,
            )
            yield _stream_event(
                "error",
                code="request_timeout",
                detail="The request took too long to complete.",
                trace_id=trace_id,
            )
            return
        except Exception:
            failure_code = "rag_pipeline_failed"
            record_outcome("failed")
            record_provider_error(
                "rag_pipeline",
                f"{settings.vector_store}+{settings.llm_provider}",
            )
            _record_request_observation(
                "failed",
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                turn_id=pending_turn.user_message_id,
                reasoning_mode=payload.reasoning_mode,
                first_status_ms=first_status_ms,
                provider_failure_override=True,
            )
            logger.exception("rag_failed trace_id=%s", trace_id)
            yield _stream_event(
                "error",
                code="rag_temporarily_unavailable",
                detail="The grounded answer service is temporarily unavailable.",
                trace_id=trace_id,
            )
            return
        finally:
            if not stored:
                try:
                    if cancellation_scope is not None:
                        cancellation_scope.cancel()
                    settle(
                        pending_turn.user_message_id,
                        cancellation_scope.usage if cancellation_scope else None,
                        cancelled=failure_code == "stream_cancelled",
                    )
                except Exception:
                    logger.exception("usage_settlement_failed")
                _mark_turn_failed(
                    pending_turn.user_message_id,
                    session,
                    failure_code,
                )

        disconnected_after_store = await request.is_disconnected()
        if answer.answer_status != "temporarily_unavailable" and not disconnected_after_store:
            first_content_ms = int((time.perf_counter() - started_at) * 1000)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        record_outcome(answer.answer_status)
        observe_rag_completion(answer, retrieval)
        _observe_request_completion(
            payload.question,
            memory,
            answer,
            retrieval,
            latency_ms,
            turn_id=pending_turn.user_message_id,
            reasoning_mode=payload.reasoning_mode,
            first_status_ms=first_status_ms,
            first_content_ms=first_content_ms,
            disconnected=disconnected_after_store,
        )
        _log_rag_completion(answer, latency_ms)
        final_response = {
            "conversation_id": conversation.conversation_id,
            "answer": _public_answer_payload(answer),
            "latency_ms": latency_ms,
            "retrieval_score": best_score,
            "token_usage": answer.debug.get(
                "token_usage",
                {"prompt_tokens": 0, "completion_tokens": 0},
            ),
            "reasoning_mode": payload.reasoning_mode,
        }
        if idempotency_key is not None and answer.answer_status != "temporarily_unavailable":
            idempotency_store.remember(
                active_user.user_id,
                idempotency_key,
                {"request": fingerprint, "response": final_response},
            )
        if disconnected_after_store:
            return
        if first_content_ms is not None:
            yield _stream_event("delta", content=answer.answer)
        yield _stream_event("done", response=final_response)

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _owned_conversations(active_user: UserRecord, session: Session) -> list[Conversation]:
    if active_user.roles == ["guest"]:
        guest_id = active_user.user_id.removeprefix("guest:")
        return (
            session.query(Conversation)
            .filter(Conversation.guest_id == guest_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
    return (
        session.query(Conversation)
        .filter(Conversation.user_id == active_user.user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.get("/export")
def export_my_data(
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> dict:
    """Export the caller's own conversations and messages (data portability)."""
    active_user = user or _anonymous_user(guest_id)
    exported = []
    for conversation in _owned_conversations(active_user, session):
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.conversation_id)
            .order_by(Message.sequence_no, Message.message_id)
            .all()
        )
        exported.append(
            {
                "conversation_id": conversation.conversation_id,
                "title": conversation.title,
                "personalized_mode": conversation.personalized_mode,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
                "messages": [
                    {
                        "role": item.role,
                        "content": item.content,
                        "created_at": item.created_at,
                    }
                    for item in messages
                ],
            }
        )
    profile = session.get(WorkProfile, active_user.user_id) if user else None
    work_profile = None
    if profile is not None:
        work_profile = {
            "province": profile.province,
            "employment_status": profile.employment_status,
            "start_date": profile.start_date.date().isoformat() if profile.start_date else None,
            "monthly_wage": profile.monthly_wage,
        }
    return {"user_id": active_user.user_id, "work_profile": work_profile, "conversations": exported}


def purge_expired_conversations(session: Session, retention_days: int) -> dict[str, int]:
    """Delete conversations (and messages) untouched for retention_days."""
    from datetime import timedelta

    cutoff = now_utc() - timedelta(days=max(1, retention_days))
    stale_ids = [
        row.conversation_id
        for row in session.query(Conversation.conversation_id)
        .filter(Conversation.updated_at < cutoff)
        .all()
    ]
    messages_deleted = 0
    if stale_ids:
        messages_deleted = (
            session.query(Message)
            .filter(Message.conversation_id.in_(stale_ids))
            .delete(synchronize_session=False)
        )
        session.query(Conversation).filter(Conversation.conversation_id.in_(stale_ids)).delete(
            synchronize_session=False
        )
        session.commit()
    return {"conversations": len(stale_ids), "messages": int(messages_deleted or 0)}


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> list[ConversationSummary]:
    if user is None:
        _anonymous_user(guest_id)
        return []
    conversations = (
        session.query(Conversation)
        .filter(Conversation.user_id == user.user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [_conversation_summary(item, session) for item in conversations]


@router.get("/usage")
def my_token_usage(
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> dict:
    active_user = user or _anonymous_user(guest_id)
    return snapshot(active_user.user_id, session)


@router.post("/conversations/{conversation_id}/claim", response_model=ConversationSummary)
def claim_guest_conversation(
    conversation_id: str,
    session: DbSession,
    user: CurrentUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> ConversationSummary:
    conversation = session.execute(
        select(Conversation)
        .where(Conversation.conversation_id == conversation_id)
        .with_for_update()
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation was not found.")
    if conversation.user_id == user.user_id:
        return _conversation_summary(conversation, session)
    if conversation.user_id:
        raise HTTPException(status_code=403, detail="Conversation belongs to another user.")
    normalized_guest_id = _anonymous_user(guest_id).user_id.removeprefix("guest:")
    if not conversation.guest_id or conversation.guest_id != normalized_guest_id:
        raise HTTPException(status_code=403, detail="Conversation belongs to another guest.")
    transfer_conversation(session, conversation_id, f"guest:{normalized_guest_id}", user.user_id)
    conversation.user_id = user.user_id
    conversation.guest_id = None
    session.commit()
    return _conversation_summary(conversation, session)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> ConversationDetail:
    active_user = user or _anonymous_user(guest_id)
    conversation = _get_owned_conversation(conversation_id, active_user, session)
    messages = (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.sequence_no, Message.message_id)
        .all()
    )
    return ConversationDetail(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        personalized_mode=conversation.personalized_mode,
        messages=[
            MessageResponse(
                **{
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                    "metadata": _public_message_metadata(m.meta_data),
                }
            )
            for m in messages
        ],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.patch(
    "/conversations/{conversation_id}/personalized-mode",
    response_model=ConversationSummary,
)
def update_personalized_mode(
    conversation_id: str,
    payload: PersonalizedModeUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> ConversationSummary:
    conversation = _get_owned_conversation(conversation_id, user, session)
    if conversation.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="A guest conversation must be claimed first.")
    conversation.personalized_mode = payload.personalized_mode
    conversation.updated_at = now_utc()
    session.commit()
    return _conversation_summary(conversation, session)


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> ConversationSummary:
    active_user = user or _anonymous_user(guest_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conversation title cannot be empty.",
        )
    conversation = _get_owned_conversation(conversation_id, active_user, session)
    conversation.title = title
    conversation.updated_at = now_utc()
    session.commit()
    return _conversation_summary(conversation, session)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: str,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> None:
    active_user = user or _anonymous_user(guest_id)
    conversation = _get_owned_conversation(conversation_id, active_user, session)
    session.query(Message).filter(Message.conversation_id == conversation_id).delete()
    session.delete(conversation)
    session.commit()
