from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.answering.generator import DISCLAIMER_EN, DISCLAIMER_ID, _detect_language
from app.services.answering.prompts import default_prompt_template
from app.services.answering.schemas import AnswerResponse

GUARDRAIL_REFUSAL = (
    "Saya tidak dapat mengikuti instruksi yang mencoba mengubah aturan sistem, "
    "mengungkap konfigurasi internal, atau mengambil kredensial. Silakan ajukan "
    "pertanyaan tentang regulasi ketenagakerjaan."
)
GUARDRAIL_REFUSAL_EN = (
    "I cannot follow instructions that attempt to change system rules, reveal internal "
    "configuration, or obtain credentials. Please ask about Indonesian employment regulations."
)

_INJECTION_PATTERNS = (
    re.compile(r"\babaikan (semua )?instruksi (sebelumnya|di atas)\b", re.IGNORECASE),
    re.compile(r"\bignore (all )?(previous|prior) instructions?\b", re.IGNORECASE),
    re.compile(
        r"\b(ungkap|tampilkan|cetak).{0,24}\b(system prompt|developer message)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(api[- ]?key|access token|password|credential).{0,20}"
        r"\b(ungkap|tampilkan|beri)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(jailbreak|do anything now|developer mode)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str | None = None


def evaluate_input_guardrail(query: str) -> GuardrailDecision:
    normalized = " ".join(query.split())
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized):
            return GuardrailDecision(allowed=False, reason="prompt_injection_detected")
    return GuardrailDecision(allowed=True)


def build_guardrail_refusal(query: str, reason: str) -> AnswerResponse:
    lang = _detect_language(query)
    disclaimer = DISCLAIMER_ID if lang == "id" else DISCLAIMER_EN
    return AnswerResponse(
        query=query,
        answer=GUARDRAIL_REFUSAL if lang == "id" else GUARDRAIL_REFUSAL_EN,
        citations=[],
        confidence=0.0,
        related_documents=[],
        refusal_reason=reason,
        clarification_question=None,
        disclaimer=disclaimer,
        prompt_version_id=default_prompt_template().prompt_version_id,
        retrieved_chunk_ids=[],
        warnings=["input_guardrail_triggered"],
        debug={"guardrail": {"blocked": True, "reason": reason}},
        answer_status="refused",
    )
