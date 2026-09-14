from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import DbSession, OptionalUser
from app.api.schemas import (
    AskRequest,
    AskResponse,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdateRequest,
    MessageResponse,
)
from app.api.state import UserRecord, now_utc
from app.api.utils import storage_root
from app.core.config import settings
from app.db.session import create_session
from app.models.business import Conversation, DailyUsage, Message
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
from app.services.answering.prompts import PROMPT_VERSION_ID
from app.services.idempotency import IdempotencyStore, valid_idempotency_key
from app.services.providers import (
    answer_generator_from_settings,
    pinecone_store_from_settings,
)
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.governance import load_retrieval_governance
from app.services.retrieval.store import load_artifact_documents_snapshot
from app.services.telemetry import (
    observe_rag_completion,
    observe_stage,
    record_outcome,
    record_provider_error,
    trace_stage,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("kerjapedia.rag")
_STREAM_TOKEN_RE = re.compile(r"\S[^\n]*\s*")
_PENDING_TURN_TTL = timedelta(minutes=5)
_HEARTBEAT_SECONDS = 15.0

idempotency_store = IdempotencyStore(redis_url=settings.redis_url)


def _idempotency_request_fingerprint(payload: AskRequest) -> dict:
    return {
        "question": payload.question,
        "conversation_id": payload.conversation_id,
        "top_k": payload.top_k,
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


def _retrieve(memory: MemoryContext, top_k: int, session: Session):
    governance = load_retrieval_governance(
        session,
        allow_unpublished=settings.rag_allow_unpublished,
    )
    # Release the read transaction before calling external retrieval providers.
    session.rollback()
    if settings.vector_store == "pinecone":
        if settings.app_env.lower() == "production" and not governance.active_namespace:
            raise RuntimeError("No validated active RAG index release is available.")
        if settings.app_env.lower() == "production" and not governance.release_consistent:
            raise RuntimeError("The active RAG release is stale and must be replaced.")
        expected_models = {
            "embedding": settings.embedding_model,
            "reranker": settings.reranker_model,
            "generator": settings.openrouter_model,
            "verifier": settings.claim_verifier_model,
            "prompt": PROMPT_VERSION_ID,
        }
        if settings.app_env.lower() == "production" and governance.active_models != expected_models:
            raise RuntimeError("The active RAG release model provenance does not match runtime.")
        retrieval = pinecone_store_from_settings(
            settings,
            namespace=governance.active_namespace,
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
            index_namespace=governance.active_namespace,
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


def _retrieve_with_isolated_session(memory: MemoryContext, top_k: int):
    """Run threaded retrieval without sharing the request SQLAlchemy session."""
    with create_session() as isolated_session:
        return _retrieve(memory, top_k, isolated_session)


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
            "turn_status": "failed",
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


def _record_usage(conversation: Conversation, answer) -> None:
    """Persist per-identity token metering in an isolated session.

    Isolation guarantees a metering failure can never poison the chat
    turn's own transaction (a poisoned transaction fails everything
    after it, including the answer insert).
    """
    try:
        from datetime import date

        usage = answer.debug.get(
            "token_usage", {"prompt_tokens": 0, "completion_tokens": 0}
        )
        user_key = _usage_key(conversation)
        today = date.today()
        with create_session() as metering_session:
            row = metering_session.get(
                DailyUsage, {"user_key": user_key, "usage_date": today}
            )
            if row is None:
                row = DailyUsage(
                    user_key=user_key,
                    usage_date=today,
                    requests=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                )
                metering_session.add(row)
            row.requests = int(row.requests or 0) + 1
            row.prompt_tokens = int(row.prompt_tokens or 0) + int(
                usage.get("prompt_tokens", 0) or 0
            )
            row.completion_tokens = int(row.completion_tokens or 0) + int(
                usage.get("completion_tokens", 0) or 0
            )
            row.updated_at = now_utc()
            metering_session.commit()
    except Exception:
        logger.exception("usage_metering_not_persisted")


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
    _record_usage(conversation, answer)
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


async def _pings_while(task: asyncio.Task):
    """Yield keepalive pings until the awaited stage finishes.

    Proxies and load balancers drop idle SSE streams; a ping every
    heartbeat interval keeps the connection (and the UI spinner) alive.
    Unknown events are ignored by the web client.
    """
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=_HEARTBEAT_SECONDS)
            if task in done:
                break
            yield _stream_event("ping")
    finally:
        if not task.done():
            task.cancel()


def _server_rag_trace(guardrail, memory, retrieval, answer) -> dict:
    retrieval_items = retrieval.results if retrieval else []
    return {
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
            "embedding_model": settings.embedding_model,
            "generator_model": settings.openrouter_model,
            "verifier_model": settings.claim_verifier_model,
            "reranker_model": settings.reranker_model,
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
        "verification": [
            {
                "cited_chunk_ids": claim.cited_chunk_ids,
                "supported": claim.supported,
                "support_score": claim.support_score,
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


def _log_rag_completion(answer, latency_ms: int) -> None:
    logger.info(
        "rag_completed trace_id=%s status=%s latency_ms=%s citations=%s "
        "prompt_version=%s answer_version=%s",
        answer.trace_id,
        answer.answer_status,
        latency_ms,
        len(answer.citations),
        answer.prompt_version_id,
        answer.answer_version,
    )


@router.post("/ask", response_model=AskResponse)
def ask_question(
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
    pending_turn = _begin_turn(conversation, payload, session)

    try:
        guardrail = evaluate_input_guardrail(payload.question)
        memory = build_memory_context(
            payload.question,
            pending_turn.previous_messages,
        )
        if not guardrail.allowed:
            answer = build_guardrail_refusal(
                payload.question,
                guardrail.reason or "input_guardrail_blocked",
            )
            retrieval = None
        else:
            retrieval_started = time.perf_counter()
            with trace_stage("retrieval", settings.vector_store):
                retrieval = _retrieve(memory, payload.top_k, session)
            observe_stage(
                "retrieval",
                settings.vector_store,
                time.perf_counter() - retrieval_started,
            )
            generation_started = time.perf_counter()
            with trace_stage("generation_and_verification", settings.llm_provider):
                answer = answer_generator_from_settings(settings).generate(
                    payload.question,
                    retrieval,
                    history=build_history_turns(pending_turn.previous_messages),
                )
            observe_stage(
                "generation_and_verification",
                settings.llm_provider,
                time.perf_counter() - generation_started,
            )
        best_score = retrieval.results[0].final_score if retrieval and retrieval.results else None
        answer, output_warnings = apply_output_guardrail(answer)
        if output_warnings:
            answer = replace(answer, warnings=[*answer.warnings, *output_warnings])
        rag_trace = _server_rag_trace(guardrail, memory, retrieval, answer)
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
    except Exception as exc:
        _mark_turn_failed(
            pending_turn.user_message_id,
            session,
            "rag_pipeline_failed",
        )
        record_outcome("failed")
        record_provider_error("rag_pipeline", f"{settings.vector_store}+{settings.llm_provider}")
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
    pending_turn = _begin_turn(conversation, payload, session)
    trace_id = f"rag_{uuid4().hex}"

    async def event_stream():
        started_at = time.perf_counter()
        stored = False
        failure_code = "stream_cancelled"
        yield _stream_event(
            "start",
            conversation_id=conversation.conversation_id,
            status="Menganalisis pertanyaan",
        )
        try:
            guardrail = evaluate_input_guardrail(payload.question)
            memory = build_memory_context(
                payload.question,
                pending_turn.previous_messages,
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
                with trace_stage("retrieval", settings.vector_store):
                    retrieval_task = asyncio.ensure_future(
                        asyncio.to_thread(
                            _retrieve_with_isolated_session,
                            memory,
                            payload.top_k,
                        )
                    )
                    async for ping in _pings_while(retrieval_task):
                        yield ping
                    retrieval = retrieval_task.result()
                observe_stage(
                    "retrieval",
                    settings.vector_store,
                    time.perf_counter() - retrieval_started,
                )
                yield _stream_event("thinking", status="Menyusun jawaban berdasarkan sumber")
                generator = answer_generator_from_settings(settings)
                history = build_history_turns(pending_turn.previous_messages)
                generation_started = time.perf_counter()
                with trace_stage("generation_and_verification", settings.llm_provider):
                    generation_task = asyncio.ensure_future(
                        asyncio.to_thread(
                            generator.generate,
                            payload.question,
                            retrieval,
                            history=history,
                        )
                    )
                    async for ping in _pings_while(generation_task):
                        yield ping
                    answer = generation_task.result()
                observe_stage(
                    "generation_and_verification",
                    settings.llm_provider,
                    time.perf_counter() - generation_started,
                )
            best_score = (
                retrieval.results[0].final_score if retrieval and retrieval.results else None
            )
            rag_trace = _server_rag_trace(guardrail, memory, retrieval, answer)
            answer.debug.update(rag_trace)
            answer = replace(answer, trace_id=trace_id)
            guarded, output_warnings = apply_output_guardrail(answer)
            if output_warnings:
                answer = replace(guarded, warnings=[*guarded.warnings, *output_warnings])
            _store_answer(
                conversation,
                pending_turn.user_message_id,
                answer,
                best_score,
                rag_trace,
                session,
            )
            stored = True
        except Exception:
            failure_code = "rag_pipeline_failed"
            record_outcome("failed")
            record_provider_error(
                "rag_pipeline",
                f"{settings.vector_store}+{settings.llm_provider}",
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
                _mark_turn_failed(
                    pending_turn.user_message_id,
                    session,
                    failure_code,
                )

        if answer.answer_status != "temporarily_unavailable":
            for token in _STREAM_TOKEN_RE.findall(answer.answer):
                if await request.is_disconnected():
                    return
                yield _stream_event("delta", content=token)
                await asyncio.sleep(0.012)

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        record_outcome(answer.answer_status)
        observe_rag_completion(answer, retrieval)
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
        }
        if idempotency_key is not None and answer.answer_status != "temporarily_unavailable":
            idempotency_store.remember(
                active_user.user_id,
                idempotency_key,
                {"request": fingerprint, "response": final_response},
            )
        yield _stream_event("done", response=final_response)

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _owned_conversations(
    active_user: UserRecord, session: Session
) -> list[Conversation]:
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
    return {"user_id": active_user.user_id, "conversations": exported}


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
        session.query(Conversation).filter(
            Conversation.conversation_id.in_(stale_ids)
        ).delete(synchronize_session=False)
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
