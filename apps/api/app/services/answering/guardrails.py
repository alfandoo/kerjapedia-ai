from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, replace

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
    re.compile(
        r"\babaikan (semua )?(instruksi|aturan|perintah)( sebelumnya| di atas| ini)?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\blupakan (semua )?(instruksi|aturan|perintah)\b", re.IGNORECASE),
    re.compile(
        r"\bignore (all )?(previous|prior|your|the) (instructions?|rules?)\b",
        re.IGNORECASE,
    ),
    # Roleplay framing is anchored to sentence start addressing the assistant
    # ("kamu sekarang adalah ...") so legitimate prose like "perusahaan
    # bertindak sebagai pemberi kerja" never matches.
    re.compile(
        r"^\s*(kamu|anda|kau|you)\s+(sekarang\s+)?(adalah|bertindak)\s+sebagai\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(ungkap|tampilkan|cetak|bocorkan|beberkan|bongkar|spill|leak|reveal)"
        r".{0,24}\b(system prompt|developer message)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(api[- ]?key|access token|password|credential).{0,20}"
        r"\b(ungkap|tampilkan|beri|bocorkan|spill|leak)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(jailbreak|do anything now|developer mode|act as|roleplay)\b",
        re.IGNORECASE,
    ),
)

# Homoglyphs abused to dodge keyword matching (Cyrillic/Greek lookalikes).
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
        "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "к": "k", "м": "m",
        "т": "t", "в": "b", "у": "y", "ԝ": "w", "ԛ": "q", "ԁ": "d",
        "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ς": "s", "ι": "i",
        "κ": "k", "μ": "m", "τ": "t", "χ": "x", "β": "b", "ν": "v",
        "υ": "u", "ζ": "z", "η": "n",
    }
)
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")
_BASE64_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/=])")

# Secrets that must never leave in an answer; matched values are redacted.
_SECRET_PATTERNS = (
    re.compile(r"\bgsk_[A-Za-z0-9]+"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9\-_]{8,}"),
    re.compile(r"\bxox[bpars]-[A-Za-z0-9\-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]{8,})?"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?\S+"
    ),
)
_ECHO_NGRAM = 8

# PII patterns that should be redacted from context chunks before LLM submission.
# NIK = Nomor Induk Kependudukan (Indonesian 16-digit national ID).
_NIK_RE = re.compile(r"\b\d{16}\b")
_PHONE_RE = re.compile(r"\b(?:\+62|62|0)8[1-9][\d\s-]{7,12}\b")
_NPWP_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}\.\d{1}-\d{3}\.\d{3}\b")

# Prompt-injection patterns that may appear inside retrieved document chunks
# (e.g., adversarial text embedded in regulation PDFs).
_CONTEXT_INJECTION_PATTERNS = (
    re.compile(
        r"\b(ignore|disregard|override|replace)\b.{0,30}\b(system|instructions?|rules?|prompt)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(you are|act as|pretend to be|roleplay as)\b"
        r".{0,20}\b(a |an |the )?(assistant|ai|bot|model)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(ungkap|tampilkan|bocorkan|beberkan|spill|leak|reveal)\b.{0,24}\b"
        r"(system prompt|developer message|konfigurasi|instruksi)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(api[- ]?key|access token|password|credential|secret)\b.{0,20}"
        r"\b(ungkap|tampilkan|beri|bocorkan|spill|leak|reveal|send|return|print)\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class ContextGuardrailDecision:
    allowed: bool
    flagged_chunk_ids: list[str] = ()
    reason: str | None = None


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str | None = None


def normalize_for_detection(text: str) -> str:
    """Fold camouflage before pattern matching: NFKC, zero-width removal,
    homoglyph folding. Matching stays on the normalized view."""
    folded = unicodedata.normalize("NFKC", text)
    folded = _ZERO_WIDTH_RE.sub(" ", folded)
    return folded.translate(_CONFUSABLES)


def _decoded_base64_spans(text: str) -> list[str]:
    """Decode long base64-looking tokens; attackers hide instructions in them."""
    decoded = []
    for token in set(_BASE64_TOKEN_RE.findall(text)):
        if len(token) % 4 != 0:
            continue
        try:
            raw = base64.b64decode(token, validate=True)
            candidate = raw.decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if candidate and sum(char.isprintable() for char in candidate) / len(candidate) > 0.9:
            decoded.append(candidate)
    return decoded


def evaluate_input_guardrail(query: str) -> GuardrailDecision:
    normalized = normalize_for_detection(" ".join(query.split()))
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized):
            return GuardrailDecision(allowed=False, reason="prompt_injection_detected")
    for candidate in _decoded_base64_spans(query):
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(normalize_for_detection(candidate)):
                return GuardrailDecision(allowed=False, reason="prompt_injection_detected")
    return GuardrailDecision(allowed=True)


def evaluate_context_guardrail(
    chunks: list,
) -> ContextGuardrailDecision:
    """Scan retrieved context chunks for embedded prompt-injection attempts.

    Returns a decision with any flagged chunk IDs so the caller can exclude
    them from the LLM prompt without discarding the entire retrieval result.
    """
    flagged: list[str] = []
    for chunk in chunks:
        text = getattr(chunk, "text", "") or ""
        if not text:
            continue
        normalized = normalize_for_detection(text)
        for pattern in _CONTEXT_INJECTION_PATTERNS:
            if pattern.search(normalized):
                chunk_id = getattr(chunk, "chunk_id", "unknown")
                flagged.append(chunk_id)
                break
    if flagged:
        return ContextGuardrailDecision(
            allowed=False,
            flagged_chunk_ids=flagged,
            reason="context_injection_detected",
        )
    return ContextGuardrailDecision(allowed=True)


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


def _word_ngrams(text: str, size: int) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def contains_prompt_echo(answer: str, system_prompt: str | None = None) -> bool:
    """Detect verbatim system-prompt leakage via shared word n-grams."""
    prompt = system_prompt or default_prompt_template().system_prompt
    prompt_grams = _word_ngrams(prompt, _ECHO_NGRAM)
    if not prompt_grams:
        return False
    return not _word_ngrams(answer, _ECHO_NGRAM).isdisjoint(prompt_grams)


def redact_secrets(text: str) -> tuple[str, bool]:
    """Mask credential-looking values; returns (cleaned, redacted_any)."""
    redacted = False
    for pattern in _SECRET_PATTERNS:
        text, count = pattern.subn("[redacted]", text)
        redacted = redacted or count > 0
    return text, redacted


def redact_context_pii(text: str) -> tuple[str, bool]:
    """Redact PII from context chunks before sending to LLM.

    Handles Indonesian NIK (16-digit national ID), phone numbers, and NPWP
    (tax ID). Returns (cleaned_text, was_redacted).
    """
    redacted = False
    for pattern in (_NIK_RE, _PHONE_RE, _NPWP_RE):
        text, count = pattern.subn("[PII]", text)
        redacted = redacted or count > 0
    return text, redacted


def apply_output_guardrail(answer: AnswerResponse) -> tuple[AnswerResponse, list[str]]:
    """Check a generated answer before it reaches the user.

    Secret values are redacted in place; a system-prompt echo fails
    closed into a refusal. Returns (answer, warnings).
    """
    if contains_prompt_echo(answer.answer):
        refusal = build_guardrail_refusal(answer.query, "output_guardrail_blocked")
        return refusal, ["output_blocked_prompt_echo"]
    cleaned, redacted = redact_secrets(answer.answer)
    if not redacted:
        return answer, []
    return (
        replace(answer, answer=cleaned, warnings=[*answer.warnings, "output_redacted_secret"]),
        ["output_redacted_secret"],
    )
