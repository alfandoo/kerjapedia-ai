"""Atomic daily chat token quota and per-turn metering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.state import now_utc
from app.core.config import settings
from app.db.session import create_session
from app.models.business import ChatTokenUsage, DailyUsage
from app.services.retrieval.token_budget import count_tokens

WIB = ZoneInfo("Asia/Jakarta")
_RESERVATION_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class QuotaReservation:
    output_cap: int
    reserved_tokens: int


class QuotaExceeded(Exception):
    def __init__(self, reset_at: datetime) -> None:
        self.reset_at = reset_at
        super().__init__("Daily token quota exceeded.")


def usage_day(at: datetime | None = None):
    return (at or now_utc()).astimezone(WIB).date()


def reset_at(at: datetime | None = None) -> datetime:
    local = (at or now_utc()).astimezone(WIB)
    return datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), WIB)


def limit_for(identity_key: str) -> int:
    return (
        settings.guest_daily_token_limit
        if identity_key.startswith("guest:")
        else settings.user_daily_token_limit
    )


def _ensure_daily(session: Session, identity_key: str, day) -> DailyUsage:
    session.execute(
        pg_insert(DailyUsage)
        .values(
            user_key=identity_key,
            usage_date=day,
            requests=0,
            prompt_tokens=0,
            completion_tokens=0,
            updated_at=now_utc(),
        )
        .on_conflict_do_nothing(index_elements=["user_key", "usage_date"])
    )
    return session.execute(
        select(DailyUsage)
        .where(DailyUsage.user_key == identity_key, DailyUsage.usage_date == day)
        .with_for_update()
    ).scalar_one()


def _pending(session: Session, identity_key: str, day) -> int:
    return int(
        session.execute(
            select(func.coalesce(func.sum(ChatTokenUsage.reserved_tokens), 0)).where(
                ChatTokenUsage.identity_key == identity_key,
                ChatTokenUsage.usage_date == day,
                ChatTokenUsage.status == "pending",
            )
        ).scalar_one()
    )


def reserve(
    *,
    identity_key: str,
    conversation_id: str,
    turn_id: str,
    question: str,
    previous_messages: list[dict],
) -> QuotaReservation:
    day = usage_day()
    history = " ".join(str(item.get("content", "")) for item in previous_messages[-4:])
    estimated_prompt = max(2000, count_tokens(question + " " + history) + 3500)
    provider_max = (
        settings.groq_max_tokens
        if settings.llm_provider == "groq"
        else settings.openrouter_max_tokens
        if settings.llm_provider == "openrouter"
        else 1000
    )
    verifier_budget = 1200 if settings.claim_verifier_provider in ("groq", "openrouter") else 0
    with create_session() as session:
        daily = _ensure_daily(session, identity_key, day)
        # A dead worker must not permanently consume the day's reservation.
        stale = session.execute(
            select(ChatTokenUsage)
            .where(
                ChatTokenUsage.identity_key == identity_key,
                ChatTokenUsage.usage_date == day,
                ChatTokenUsage.status == "pending",
                ChatTokenUsage.created_at < now_utc() - _RESERVATION_TTL,
            )
            .with_for_update()
        ).scalars()
        for item in stale:
            if item.provider_started:
                daily.prompt_tokens = int(daily.prompt_tokens or 0) + item.reserved_tokens
                daily.requests = int(daily.requests or 0) + 1
                item.prompt_tokens = item.reserved_tokens
                item.source = "estimated"
            item.status = "expired"
            item.reserved_tokens = 0
            item.updated_at = now_utc()
        session.flush()
        existing = session.get(ChatTokenUsage, turn_id)
        if existing is not None:
            if existing.status != "pending" or existing.identity_key != identity_key:
                raise RuntimeError("Token reservation identity or state mismatch.")
            session.commit()
            return QuotaReservation(
                output_cap=max(
                    512,
                    existing.reserved_tokens - existing.estimated_prompt_tokens - verifier_budget,
                ),
                reserved_tokens=existing.reserved_tokens,
            )
        used = int(daily.prompt_tokens or 0) + int(daily.completion_tokens or 0)
        available = limit_for(identity_key) - used - _pending(session, identity_key, day)
        minimum = estimated_prompt + verifier_budget + 512
        if available < minimum:
            raise QuotaExceeded(reset_at())
        reserved = min(available, estimated_prompt + verifier_budget + provider_max)
        output_cap = min(provider_max, reserved - estimated_prompt - verifier_budget)
        session.add(
            ChatTokenUsage(
                turn_id=turn_id,
                conversation_id=conversation_id,
                identity_key=identity_key,
                usage_date=day,
                reserved_tokens=reserved,
                estimated_prompt_tokens=estimated_prompt,
                source="pending",
                status="pending",
            )
        )
        session.commit()
        return QuotaReservation(output_cap=output_cap, reserved_tokens=reserved)


def mark_provider_started(turn_id: str) -> None:
    with create_session() as session:
        item = session.get(ChatTokenUsage, turn_id)
        if item is None or item.status != "pending":
            raise RuntimeError("Token reservation is not active.")
        item.provider_started = True
        item.updated_at = now_utc()
        session.commit()


def settle(
    turn_id: str,
    usage: dict | None = None,
    answer_text: str = "",
    *,
    cancelled: bool = False,
) -> None:
    with create_session() as session:
        item = session.get(ChatTokenUsage, turn_id)
        if item is None:
            raise RuntimeError("Token reservation is missing.")
        daily = _ensure_daily(session, item.identity_key, item.usage_date)
        item = session.execute(
            select(ChatTokenUsage).where(ChatTokenUsage.turn_id == turn_id).with_for_update()
        ).scalar_one()
        if item.status != "pending":
            session.commit()
            return
        supplied_prompt = max(0, int((usage or {}).get("prompt_tokens", 0) or 0))
        supplied_completion = max(0, int((usage or {}).get("completion_tokens", 0) or 0))
        if not item.provider_started:
            prompt, completion, source = 0, 0, "none"
        elif cancelled:
            prompt = supplied_prompt or item.estimated_prompt_tokens
            completion = supplied_completion
            source = "provider" if supplied_prompt + supplied_completion else "estimated"
        elif supplied_prompt + supplied_completion > 0:
            prompt = supplied_prompt or item.estimated_prompt_tokens
            completion = supplied_completion or (
                max(1, count_tokens(answer_text)) if answer_text else 0
            )
            source = (
                "provider"
                if supplied_prompt and (supplied_completion or not answer_text)
                else "estimated"
            )
        elif answer_text:
            prompt = item.estimated_prompt_tokens
            completion = max(1, count_tokens(answer_text))
            source = "estimated"
        else:
            prompt, completion, source = item.reserved_tokens, 0, "estimated"
        item.prompt_tokens = prompt
        item.completion_tokens = completion
        item.reserved_tokens = 0
        item.source = source
        item.status = "cancelled" if cancelled else "completed"
        item.updated_at = now_utc()
        daily.requests = int(daily.requests or 0) + int(item.provider_started)
        daily.prompt_tokens = int(daily.prompt_tokens or 0) + prompt
        daily.completion_tokens = int(daily.completion_tokens or 0) + completion
        daily.updated_at = now_utc()
        session.commit()


def snapshot(identity_key: str, session: Session) -> dict:
    day = usage_day()
    row = session.get(DailyUsage, {"user_key": identity_key, "usage_date": day})
    used_prompt = int(row.prompt_tokens or 0) if row else 0
    used_completion = int(row.completion_tokens or 0) if row else 0
    reserved = _pending(session, identity_key, day)
    limit = limit_for(identity_key)
    return {
        "usage_date": day.isoformat(),
        "timezone": "Asia/Jakarta",
        "reset_at": reset_at().isoformat(),
        "limit_tokens": limit,
        "prompt_tokens": used_prompt,
        "completion_tokens": used_completion,
        "used_tokens": used_prompt + used_completion,
        "reserved_tokens": reserved,
        "remaining_tokens": max(0, limit - used_prompt - used_completion - reserved),
        "estimated_tokens": int(
            session.execute(
                select(
                    func.coalesce(
                        func.sum(ChatTokenUsage.prompt_tokens + ChatTokenUsage.completion_tokens), 0
                    )
                ).where(
                    ChatTokenUsage.identity_key == identity_key,
                    ChatTokenUsage.usage_date == day,
                    ChatTokenUsage.source == "estimated",
                )
            ).scalar_one()
        ),
    }


def transfer_conversation(
    session: Session,
    conversation_id: str,
    guest_key: str,
    user_key: str,
) -> None:
    candidates = (
        session.execute(
            select(ChatTokenUsage.usage_date)
            .where(
                ChatTokenUsage.conversation_id == conversation_id,
                ChatTokenUsage.identity_key == guest_key,
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    for day in sorted(candidates):
        # Lock aggregate rows in stable key order; claims of different conversations
        # from the same guest cannot double transfer their ledger rows.
        aggregates = {
            key: _ensure_daily(session, key, day) for key in sorted((guest_key, user_key))
        }
        rows = (
            session.execute(
                select(ChatTokenUsage)
                .where(
                    ChatTokenUsage.conversation_id == conversation_id,
                    ChatTokenUsage.identity_key == guest_key,
                    ChatTokenUsage.usage_date == day,
                )
                .order_by(ChatTokenUsage.turn_id)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.status != "completed":
                raise RuntimeError("Cannot claim a conversation with pending token usage.")
            guest = aggregates[guest_key]
            user = aggregates[user_key]
            guest.prompt_tokens = max(0, int(guest.prompt_tokens or 0) - row.prompt_tokens)
            guest.completion_tokens = max(
                0, int(guest.completion_tokens or 0) - row.completion_tokens
            )
            guest.requests = max(0, int(guest.requests or 0) - int(row.provider_started))
            user.prompt_tokens = int(user.prompt_tokens or 0) + row.prompt_tokens
            user.completion_tokens = int(user.completion_tokens or 0) + row.completion_tokens
            user.requests = int(user.requests or 0) + int(row.provider_started)
            row.identity_key = user_key
            row.updated_at = now_utc()
    session.flush()
