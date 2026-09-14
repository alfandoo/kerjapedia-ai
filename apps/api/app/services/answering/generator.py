from __future__ import annotations

import re

from app.services.answering.citations import build_citations, build_related_documents, compact_text
from app.services.answering.claim_verifier import verify_claims_deterministically
from app.services.answering.prompts import default_prompt_template
from app.services.answering.schemas import AnswerResponse, HistoryTurn
from app.services.retrieval.schemas import RetrievalResponse

DISCLAIMER_ID = (
    "KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator hubungan "
    "industrial, atau instansi pemerintah. Verifikasi sumber resmi sebelum mengambil "
    "keputusan."
)
DISCLAIMER_EN = (
    "KerjaPedia AI is not a substitute for attorneys, legal consultants, industrial "
    "relations mediators, or government agencies. Verify official sources before making "
    "decisions."
)

REFUSAL_TEXT_ID = (
    "Informasi yang cukup tidak ditemukan dalam dokumen yang tersedia. "
    "Silakan perjelas konteks pertanyaan, periksa sumber resmi, atau konsultasikan "
    "dengan pihak yang berwenang."
)
REFUSAL_TEXT_EN = (
    "Sufficient information was not found in the available documents. "
    "Please clarify the question context, check official sources, or consult "
    "with the relevant authorities."
)

OUT_OF_SCOPE_TEXT_ID = (
    "Maaf, saya tidak tahu untuk pertanyaan tersebut. KerjaPedia AI difokuskan "
    "khusus pada regulasi dan persoalan ketenagakerjaan Indonesia. Silakan ajukan "
    "pertanyaan tentang hubungan kerja, PKWT, PHK, pengupahan, THR, BPJS "
    "ketenagakerjaan, K3, atau topik ketenagakerjaan lainnya."
)
OUT_OF_SCOPE_TEXT_EN = (
    "Sorry, I don't have an answer for that question. KerjaPedia AI is focused "
    "specifically on Indonesian employment regulations and issues. Please ask "
    "questions about employment relationships, fixed-term contracts (PKWT), "
    "termination (PHK), wages, THR, BPJS employment, OHS, or other employment topics."
)

CLARIFICATION_TEXT_ID = (
    "Pertanyaannya masih terlalu umum. Tolong tambahkan konteks seperti topik "
    "(PKWT, PHK, THR, serikat pekerja), status pekerja, dan tahun atau pasal "
    "jika ada."
)
CLARIFICATION_TEXT_EN = (
    "The question is still too general. Please add context such as topic "
    "(PKWT, PHK, THR, trade union), worker status, and year or article "
    "if available."
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_HIGH_RISK_TERMS = {
    "pecat",
    "phk",
    "pesangon",
    "gugat",
    "pengadilan",
    "pidana",
    "lapor",
    "sanksi",
}


def _detect_language(query: str) -> str:
    """Detect if query is primarily Indonesian or English."""
    lower = query.lower()
    _id_markers = {
        "apa",
        "bagaimana",
        "gimana",
        "kapan",
        "dimana",
        "mengapa",
        "kenapa",
        "adakah",
        "apakah",
        "berapa",
        "siapakah",
        "siapa",
        "kah",
        "yang",
        "dan",
        "atau",
        "dalam",
        "untuk",
        "dengan",
        "pada",
        "adalah",
        "ini",
        "itu",
        "dari",
        "ke",
        "kepada",
        "bayar",
        "dibayar",
        "di",
        "tidak",
        "bukan",
        "belum",
        "akan",
        "dapat",
        "harus",
        "wajib",
        "hak",
        "pekerja",
        "perusahaan",
        "undang",
        "peraturan",
        "pp",
        "ppno",
        "perppu",
        "uu",
        "pkwt",
        "phk",
        "thr",
        "bpjs",
        "k3",
        "upah",
        "gaji",
        "denda",
        "dendanya",
        "pembayaran",
        "kompensasi",
        "sanksi",
        "ketentuan",
        "berlaku",
        "komplain",
        "sanggahan",
    }
    _en_markers = {
        "what",
        "how",
        "when",
        "where",
        "why",
        "which",
        "who",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "may",
        "might",
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "this",
        "that",
        "these",
        "those",
        "not",
        "no",
        "yes",
        "if",
        "then",
        "employment",
        "worker",
        "employee",
        "employer",
        "labor",
        "labour",
        "wage",
        "salary",
        "contract",
        "compensation",
        "payment",
        "penalty",
        "deadline",
        "entitlement",
        "termination",
        "bonus",
        "insurance",
        "safety",
    }
    tokens = set(re.findall(r"[a-z]+", lower))
    id_hits = len(tokens & _id_markers)
    en_hits = len(tokens & _en_markers)
    if id_hits > en_hits:
        return "id"
    if en_hits > id_hits:
        return "en"
    non_ascii = sum(1 for c in query if ord(c) > 127)
    return "id" if non_ascii > 0 else "en"


class AnswerGenerator:
    def __init__(self, max_citations: int = 4) -> None:
        self.max_citations = max_citations
        self.prompt_template = default_prompt_template()

    def generate(
        self,
        query: str,
        retrieval: RetrievalResponse,
        *,
        history: tuple[HistoryTurn, ...] | list[HistoryTurn] | None = None,
    ) -> AnswerResponse:
        # The extractive composer answers from retrieved quotes only; history
        # is accepted for interface parity (follow-ups already resolve through
        # the memory-aware retrieval query) and recorded in debug.
        history_turns = tuple(history or [])
        needs_clarification = self._needs_clarification(query, retrieval)
        if retrieval.refusal_reason == "out_of_scope_query" and not needs_clarification:
            return self._refusal_response(
                query=query,
                retrieval=retrieval,
                refusal_reason="out_of_scope_query",
            )

        if needs_clarification:
            return self._clarification_response(query, retrieval)

        if retrieval.should_refuse:
            return self._refusal_response(
                query=query,
                retrieval=retrieval,
                refusal_reason=retrieval.refusal_reason or "insufficient_context",
            )

        selected = retrieval.results[: self.max_citations]
        citations = build_citations(selected)
        if not citations:
            return self._refusal_response(
                query=query,
                retrieval=retrieval,
                refusal_reason="no_citations_available",
            )

        answer = self._compose_grounded_answer(query, citations)
        raw_claims = [
            (compact_text(citation.quote, 220), [citation.chunk_id]) for citation in citations
        ]
        claims = verify_claims_deterministically(raw_claims, citations)
        confidence = self._estimate_confidence(retrieval)
        related_documents = build_related_documents(selected)
        lang = _detect_language(query)
        disclaimer = DISCLAIMER_ID if lang == "id" else DISCLAIMER_EN

        return AnswerResponse(
            query=query,
            answer=answer,
            citations=citations,
            confidence=confidence,
            related_documents=related_documents,
            refusal_reason=None,
            clarification_question=None,
            disclaimer=disclaimer,
            prompt_version_id=self.prompt_template.prompt_version_id,
            retrieved_chunk_ids=[item.document.chunk_id for item in selected],
            warnings=retrieval.warnings,
            debug={
                "prompt_version_id": self.prompt_template.prompt_version_id,
                "query_understanding": retrieval.query.normalized_query,
                "history_turns": len(history_turns),
            },
            claims=claims,
        )

    def _compose_grounded_answer(self, query: str, citations: list) -> str:
        lang = _detect_language(query)
        grounded_sentences = []
        for citation in citations:
            legal_ref = ", ".join(
                part
                for part in [citation.short_title, citation.article, citation.paragraph]
                if part
            )
            quote = compact_text(citation.quote, 220).rstrip(" .")
            grounded_sentences.append(f"{quote}. ({legal_ref})" if legal_ref else f"{quote}.")

        if lang == "id":
            if self._contains_high_risk_term(query):
                opening = (
                    "Berdasarkan dokumen yang tersedia, berikut ringkasan awal yang perlu "
                    "diverifikasi lebih lanjut."
                )
            else:
                opening = "Berdasarkan regulasi yang berlaku, jawabannya adalah sebagai berikut."
            closing = (
                "Untuk penerapan pada kasus tertentu, periksa kembali dokumen dan "
                "sumber resmi terkait."
            )
        else:
            if self._contains_high_risk_term(query):
                opening = (
                    "Based on the available documents, this is an initial summary that "
                    "requires further verification."
                )
            else:
                opening = "Based on the applicable regulations, the answer is as follows."
            closing = "For a specific case, verify the applicable documents and official sources."

        body = " ".join(grounded_sentences)
        return "\n\n".join(part for part in [opening, body, closing] if part)

    def _needs_clarification(self, query: str, retrieval: RetrievalResponse) -> bool:
        tokens = _TOKEN_RE.findall(query.lower())
        has_topic = bool(retrieval.query.detected_topics)
        has_intent = bool(retrieval.query.detected_intents)
        _id_tokens = {"hak", "saya", "aturan", "gimana", "bagaimana"}
        _en_tokens = {"rights", "my", "rule", "how"}
        query_tokens = set(tokens)
        if (
            len(tokens) <= 3
            and not has_topic
            and (query_tokens & _id_tokens or query_tokens & _en_tokens)
        ):
            return True
        if (query_tokens & _id_tokens or query_tokens & _en_tokens) and not (
            has_topic or has_intent
        ):
            return True
        return False

    def _clarification_response(
        self,
        query: str,
        retrieval: RetrievalResponse,
    ) -> AnswerResponse:
        lang = _detect_language(query)
        question = CLARIFICATION_TEXT_ID if lang == "id" else CLARIFICATION_TEXT_EN
        return AnswerResponse(
            query=query,
            answer=question,
            citations=[],
            confidence=0.0,
            related_documents=[],
            refusal_reason=None,
            clarification_question=question,
            disclaimer=DISCLAIMER_ID if lang == "id" else DISCLAIMER_EN,
            prompt_version_id=self.prompt_template.prompt_version_id,
            retrieved_chunk_ids=[],
            warnings=retrieval.warnings,
            debug={
                "prompt_version_id": self.prompt_template.prompt_version_id,
                "query_understanding": retrieval.query.normalized_query,
            },
            answer_status="clarification",
        )

    def _refusal_response(
        self,
        query: str,
        retrieval: RetrievalResponse,
        refusal_reason: str,
    ) -> AnswerResponse:
        lang = _detect_language(query)
        if lang == "id":
            refusal_text = (
                OUT_OF_SCOPE_TEXT_ID if refusal_reason == "out_of_scope_query" else REFUSAL_TEXT_ID
            )
            disclaimer = DISCLAIMER_ID
        else:
            refusal_text = (
                OUT_OF_SCOPE_TEXT_EN if refusal_reason == "out_of_scope_query" else REFUSAL_TEXT_EN
            )
            disclaimer = DISCLAIMER_EN
        return AnswerResponse(
            query=query,
            answer=refusal_text,
            citations=[],
            confidence=0.0,
            related_documents=[],
            refusal_reason=refusal_reason,
            clarification_question=None,
            disclaimer=disclaimer,
            prompt_version_id=self.prompt_template.prompt_version_id,
            retrieved_chunk_ids=[],
            warnings=retrieval.warnings,
            debug={
                "prompt_version_id": self.prompt_template.prompt_version_id,
                "query_understanding": retrieval.query.normalized_query,
            },
            answer_status="refused",
        )

    def _estimate_confidence(self, retrieval: RetrievalResponse) -> float:
        if not retrieval.results:
            return 0.0

        best_score = min(retrieval.results[0].final_score, 1.0)
        citation_coverage = min(len(retrieval.results) / self.max_citations, 1.0)
        warning_penalty = 0.15 if retrieval.warnings else 0.0
        confidence = (best_score * 0.75) + (citation_coverage * 0.25) - warning_penalty
        return round(max(0.05, min(confidence, 0.95)), 3)

    def _contains_high_risk_term(self, query: str) -> bool:
        tokens = set(_TOKEN_RE.findall(query.lower()))
        return bool(tokens.intersection(_HIGH_RISK_TERMS))
