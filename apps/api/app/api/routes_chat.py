from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import asdict
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
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
from app.api.utils import dataset_metadata_path, storage_root
from app.core.config import settings
from app.models.business import Conversation, Message
from app.services.answering.guardrails import build_guardrail_refusal, evaluate_input_guardrail
from app.services.answering.memory import MemoryContext, build_memory_context
from app.services.providers import answer_generator_from_settings, pinecone_store_from_settings
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.relationships import relationship_index_for_manifest
from app.services.retrieval.store import load_artifact_documents

router = APIRouter(prefix="/chat", tags=["chat"])
_STREAM_TOKEN_RE = re.compile(r"\S[^\n]*\s*")


def _anonymous_user(guest_id: str | None = None) -> UserRecord:
    if guest_id:
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
    return UserRecord(
        user_id="anonymous",
        email="anonymous@local",
        name="anonymous",
        roles=["guest"],
    )


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
        return conversation

    conversation_id = f"conv_{uuid4().hex}"
    title = payload.question[:80]
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
) -> list[dict[str, str]]:
    rows = (
        session.query(Message)
        .filter(Message.conversation_id == conversation.conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in reversed(rows)]


def _retrieve(question: str, top_k: int):
    if settings.vector_store == "pinecone":
        return pinecone_store_from_settings(settings).search(question, top_k=top_k)
    documents = load_artifact_documents(storage_root())
    index = relationship_index_for_manifest(dataset_metadata_path())
    return RetrievalEngine(
        documents=documents,
        top_k=top_k,
        relationship_index=index,
    ).search(question, top_k=top_k)


def _store_answer(
    conversation: Conversation,
    payload: AskRequest,
    answer,
    best_score,
    rag_trace: dict | None = None,
    session: Session | None = None,
) -> None:
    if session is None:
        return
    now = now_utc()

    user_msg = Message(
        message_id=f"msg_{uuid4().hex}",
        conversation_id=conversation.conversation_id,
        role="user",
        content=payload.question,
        meta_data={"rag_trace": rag_trace or {}},
    )
    session.add(user_msg)

    asst_msg = Message(
        message_id=f"msg_{uuid4().hex}",
        conversation_id=conversation.conversation_id,
        role="assistant",
        content=answer.answer,
        meta_data={
            "answer": asdict(answer),
            "retrieval_score": best_score,
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0},
            "rag_trace": rag_trace or {},
        },
    )
    session.add(asst_msg)
    conversation.updated_at = now
    session.commit()


def _generator_query(question: str, memory: MemoryContext) -> str:
    if not memory.used:
        return question
    return f'{question} (konteks percakapan sebelumnya: {memory.retrieval_query})'


def _stream_event(event: str, **payload) -> bytes:
    serialized = json.dumps(
        {"event": event, **payload},
        ensure_ascii=False,
        default=str,
    )
    return f"{serialized}\n".encode()


@router.post("/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> AskResponse:
    started_at = time.perf_counter()
    active_user = user or _anonymous_user(guest_id)
    conversation = _get_or_create_conversation(payload, active_user, session)

    try:
        guardrail = evaluate_input_guardrail(payload.question)
        memory = build_memory_context(
            payload.question,
            _recent_messages(conversation, session),
        )
        if not guardrail.allowed:
            answer = build_guardrail_refusal(
                payload.question,
                guardrail.reason or "input_guardrail_blocked",
            )
            retrieval = None
        else:
            retrieval = _retrieve(memory.retrieval_query, payload.top_k)
            answer = answer_generator_from_settings(settings).generate(
                _generator_query(payload.question, memory),
                retrieval,
            )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    best_score = retrieval.results[0].final_score if retrieval and retrieval.results else None
    rag_trace = {
        "guardrail": {"allowed": guardrail.allowed, "reason": guardrail.reason},
        "memory": {
            "used": memory.used,
            "source_turns": memory.source_turns,
            "retrieval_query": memory.retrieval_query,
        },
    }
    answer.debug.update(rag_trace)

    _store_answer(conversation, payload, answer, best_score, rag_trace, session)

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    return AskResponse(
        conversation_id=conversation.conversation_id,
        answer=asdict(answer),
        latency_ms=latency_ms,
        retrieval_score=best_score,
        token_usage={"prompt_tokens": 0, "completion_tokens": 0},
    )


@router.post("/ask/stream")
def ask_question_stream(
    payload: AskRequest,
    request: Request,
    session: DbSession,
    user: OptionalUser,
    guest_id: str | None = Header(default=None, alias="X-KerjaPedia-Guest-ID"),
) -> StreamingResponse:
    active_user = user or _anonymous_user(guest_id)
    conversation = _get_or_create_conversation(payload, active_user, session)

    async def event_stream():
        started_at = time.perf_counter()
        yield _stream_event(
            "start",
            conversation_id=conversation.conversation_id,
            status="Menganalisis pertanyaan",
        )
        try:
            guardrail = evaluate_input_guardrail(payload.question)
            memory = build_memory_context(
                payload.question,
                _recent_messages(conversation, session),
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
                retrieval = await asyncio.to_thread(
                    _retrieve,
                    memory.retrieval_query,
                    payload.top_k,
                )
                yield _stream_event("thinking", status="Menyusun jawaban berdasarkan sumber")
                generator = answer_generator_from_settings(settings)
                answer = await asyncio.to_thread(
                    generator.generate,
                    _generator_query(payload.question, memory),
                    retrieval,
                )
        except RuntimeError as exc:
            yield _stream_event("error", detail=str(exc))
            return

        best_score = retrieval.results[0].final_score if retrieval and retrieval.results else None
        rag_trace = {
            "guardrail": {"allowed": guardrail.allowed, "reason": guardrail.reason},
            "memory": {
                "used": memory.used,
                "source_turns": memory.source_turns,
                "retrieval_query": memory.retrieval_query,
            },
        }
        answer.debug.update(rag_trace)
        _store_answer(conversation, payload, answer, best_score, rag_trace, session)
        for token in _STREAM_TOKEN_RE.findall(answer.answer):
            if await request.is_disconnected():
                return
            yield _stream_event("delta", content=token)
            await asyncio.sleep(0.012)

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        yield _stream_event(
            "done",
            response={
                "conversation_id": conversation.conversation_id,
                "answer": asdict(answer),
                "latency_ms": latency_ms,
                "retrieval_score": best_score,
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        .order_by(Message.created_at)
        .all()
    )
    return ConversationDetail(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        messages=[MessageResponse(**{
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
            "metadata": m.meta_data,
        }) for m in messages],
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
