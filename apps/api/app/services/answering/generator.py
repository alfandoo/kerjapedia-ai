from __future__ import annotations

import re

from app.services.answering.citations import build_citations, build_related_documents, compact_text
from app.services.answering.prompts import default_prompt_template, render_user_prompt
from app.services.answering.schemas import AnswerResponse
from app.services.retrieval.schemas import RetrievalResponse

DISCLAIMER = (
    "KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator hubungan "
    "industrial, atau instansi pemerintah. Verifikasi sumber resmi sebelum mengambil "
    "keputusan."
)

REFUSAL_TEXT = (
    "Informasi yang cukup tidak ditemukan dalam dokumen yang tersedia. "
    "Silakan perjelas konteks pertanyaan, periksa sumber resmi, atau konsultasikan "
    "dengan pihak yang berwenang."
)

OUT_OF_SCOPE_TEXT = (
    "Maaf, saya tidak tahu untuk pertanyaan tersebut. KerjaPedia AI difokuskan "
    "khusus pada regulasi dan persoalan ketenagakerjaan Indonesia. Silakan ajukan "
    "pertanyaan tentang hubungan kerja, PKWT, PHK, pengupahan, THR, BPJS "
    "ketenagakerjaan, K3, atau topik ketenagakerjaan lainnya."
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


class AnswerGenerator:
    def __init__(self, max_citations: int = 4) -> None:
        self.max_citations = max_citations
        self.prompt_template = default_prompt_template()

    def generate(self, query: str, retrieval: RetrievalResponse) -> AnswerResponse:
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
        confidence = self._estimate_confidence(retrieval)
        related_documents = build_related_documents(selected)

        return AnswerResponse(
            query=query,
            answer=answer,
            citations=citations,
            confidence=confidence,
            related_documents=related_documents,
            refusal_reason=None,
            clarification_question=None,
            disclaimer=DISCLAIMER,
            prompt_version_id=self.prompt_template.prompt_version_id,
            retrieved_chunk_ids=[item.document.chunk_id for item in selected],
            warnings=retrieval.warnings,
            debug={
                "system_prompt": self.prompt_template.system_prompt,
                "rendered_user_prompt": render_user_prompt(query, retrieval),
                "query_understanding": retrieval.query.normalized_query,
            },
        )

    def _compose_grounded_answer(self, query: str, citations: list) -> str:
        citation_lines = []
        for citation in citations:
            legal_ref = ", ".join(
                part
                for part in [
                    citation.short_title,
                    citation.article,
                    citation.paragraph,
                    f"hal. {citation.page_start}-{citation.page_end}",
                ]
                if part
            )
            citation_lines.append(
                f"- {compact_text(citation.quote, 220)} [{citation.citation_id}: {legal_ref}]"
            )

        opening = "Berdasarkan dokumen yang tersedia, poin yang paling relevan adalah:"
        if self._contains_high_risk_term(query):
            opening = (
                "Berdasarkan dokumen yang tersedia, berikut ringkasan awal yang perlu "
                "diverifikasi lebih lanjut:"
            )

        return "\n".join([opening, *citation_lines])

    def _needs_clarification(self, query: str, retrieval: RetrievalResponse) -> bool:
        tokens = _TOKEN_RE.findall(query.lower())
        has_topic = bool(retrieval.query.detected_topics)
        has_intent = bool(retrieval.query.detected_intents)
        if (
            len(tokens) <= 3
            and not has_topic
            and set(tokens) & {"hak", "saya", "aturan", "gimana", "bagaimana"}
        ):
            return True
        if any(term in tokens for term in {"hak", "aturan", "gimana", "bagaimana"}) and not (
            has_topic or has_intent
        ):
            return True
        return False

    def _clarification_response(
        self,
        query: str,
        retrieval: RetrievalResponse,
    ) -> AnswerResponse:
        question = (
            "Pertanyaannya masih terlalu umum. Tolong tambahkan konteks seperti topik "
            "(PKWT, PHK, THR, serikat pekerja), status pekerja, dan tahun atau pasal "
            "jika ada."
        )
        return AnswerResponse(
            query=query,
            answer=question,
            citations=[],
            confidence=0.0,
            related_documents=[],
            refusal_reason=None,
            clarification_question=question,
            disclaimer=DISCLAIMER,
            prompt_version_id=self.prompt_template.prompt_version_id,
            retrieved_chunk_ids=[],
            warnings=retrieval.warnings,
            debug={
                "system_prompt": self.prompt_template.system_prompt,
                "rendered_user_prompt": render_user_prompt(query, retrieval),
                "query_understanding": retrieval.query.normalized_query,
            },
        )

    def _refusal_response(
        self,
        query: str,
        retrieval: RetrievalResponse,
        refusal_reason: str,
    ) -> AnswerResponse:
        refusal_text = OUT_OF_SCOPE_TEXT if refusal_reason == "out_of_scope_query" else REFUSAL_TEXT
        return AnswerResponse(
            query=query,
            answer=refusal_text,
            citations=[],
            confidence=0.0,
            related_documents=[],
            refusal_reason=refusal_reason,
            clarification_question=None,
            disclaimer=DISCLAIMER,
            prompt_version_id=self.prompt_template.prompt_version_id,
            retrieved_chunk_ids=[],
            warnings=retrieval.warnings,
            debug={
                "system_prompt": self.prompt_template.system_prompt,
                "rendered_user_prompt": render_user_prompt(query, retrieval),
                "query_understanding": retrieval.query.normalized_query,
            },
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
