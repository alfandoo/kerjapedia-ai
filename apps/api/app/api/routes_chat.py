from __future__ import annotations

import time
from dataclasses import asdict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import OptionalUser
from app.api.schemas import (
    AskRequest,
    AskResponse,
    ConversationDetail,
    ConversationSummary,
    MessageResponse,
)
from app.api.state import ConversationRecord, UserRecord, now_utc, state
from app.api.utils import storage_root
from app.services.answering.generator import AnswerGenerator
from app.services.retrieval.engine import RetrievalEngine
from app.services.retrieval.store import load_artifact_documents

router = APIRouter(prefix="/chat", tags=["chat"])


def _anonymous_user() -> UserRecord:
    return UserRecord(
        user_id="anonymous",
        email="anonymous@local",
        name="anonymous",
        roles=["guest"],
    )


def _get_or_create_conversation(
    payload: AskRequest,
    user: UserRecord,
) -> ConversationRecord:
    with state.lock:
        if payload.conversation_id:
            existing = state.conversations.get(payload.conversation_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation was not found.",
                )
            if existing.user_id != user.user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Conversation belongs to another user.",
                )
            return existing

        conversation_id = f"conv_{uuid4().hex}"
        title = payload.question[:80]
        conversation = ConversationRecord(
            conversation_id=conversation_id,
            user_id=user.user_id,
            title=title,
        )
        state.conversations[conversation_id] = conversation
        return conversation


@router.post("/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    user: OptionalUser,
) -> AskResponse:
    started_at = time.perf_counter()
    active_user = user or _anonymous_user()
    conversation = _get_or_create_conversation(payload, active_user)

    documents = load_artifact_documents(storage_root())
    retrieval = RetrievalEngine(documents=documents, top_k=payload.top_k).search(
        payload.question,
        top_k=payload.top_k,
    )
    answer = AnswerGenerator().generate(payload.question, retrieval)
    best_score = retrieval.results[0].final_score if retrieval.results else None

    now = now_utc()
    with state.lock:
        conversation.messages.append(
            {
                "role": "user",
                "content": payload.question,
                "created_at": now,
                "metadata": {},
            }
        )
        conversation.messages.append(
            {
                "role": "assistant",
                "content": answer.answer,
                "created_at": now_utc(),
                "metadata": {
                    "answer": asdict(answer),
                    "retrieval_score": best_score,
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0},
                },
            }
        )
        conversation.updated_at = now_utc()

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    return AskResponse(
        conversation_id=conversation.conversation_id,
        answer=asdict(answer),
        latency_ms=latency_ms,
        retrieval_score=best_score,
        token_usage={"prompt_tokens": 0, "completion_tokens": 0},
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    user: OptionalUser,
) -> list[ConversationSummary]:
    active_user = user or _anonymous_user()
    conversations = [
        item for item in state.conversations.values() if item.user_id == active_user.user_id
    ]
    conversations.sort(key=lambda item: item.updated_at, reverse=True)
    return [
        ConversationSummary(
            conversation_id=item.conversation_id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
            message_count=len(item.messages),
        )
        for item in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    user: OptionalUser,
) -> ConversationDetail:
    active_user = user or _anonymous_user()
    conversation = state.conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation was not found.",
        )
    if conversation.user_id != active_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation belongs to another user.",
        )

    return ConversationDetail(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        messages=[MessageResponse(**message) for message in conversation.messages],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )
