from __future__ import annotations

import json
import re
from typing import Any

from app.services.answering.citations import build_citations, build_related_documents
from app.services.answering.generator import DISCLAIMER_ID, DISCLAIMER_EN, _detect_language, AnswerGenerator
from app.services.answering.prompts import render_user_prompt
from app.services.answering.schemas import AnswerResponse
from app.services.retrieval.schemas import RetrievalResponse


class GroqAnswerGenerator(AnswerGenerator):
    def __init__(
        self,
        api_key: str,
        model_name: str = "openai/gpt-oss-120b",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        max_tokens: int = 1200,
        max_citations: int = 4,
    ) -> None:
        super().__init__(max_citations=max_citations)
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self._client = None

    def generate(self, query: str, retrieval: RetrievalResponse) -> AnswerResponse:
        if self._needs_clarification(query, retrieval):
            return self._clarification_response(query, retrieval)

        if retrieval.should_refuse:
            return self._refusal_response(
                query=query,
                retrieval=retrieval,
                refusal_reason=retrieval.refusal_reason or "insufficient_context",
            )

        selected = retrieval.results[: self.max_citations]
        fallback_citations = build_citations(selected)
        if not fallback_citations:
            return self._refusal_response(
                query=query,
                retrieval=retrieval,
                refusal_reason="no_citations_available",
            )

        retrieved_chunk_ids = [item.document.chunk_id for item in selected]
        try:
            payload = self._call_groq(query, retrieval, retrieved_chunk_ids)
            answer = _clean_answer_text(
                str(payload.get("answer", "")).strip(),
                retrieved_chunk_ids,
            )
            cited_chunk_ids = payload.get("cited_chunk_ids")
            if not answer:
                raise ValueError("Groq returned an empty answer.")
            if not isinstance(cited_chunk_ids, list) or not cited_chunk_ids:
                raise ValueError("Groq returned no cited chunk IDs.")
            if not set(cited_chunk_ids).issubset(set(retrieved_chunk_ids)):
                raise ValueError("Groq cited chunks that were not retrieved.")
            cited_ids = set(cited_chunk_ids)
            cited_results = [
                item for item in selected if item.document.chunk_id in cited_ids
            ]
            citations = build_citations(cited_results)
            related_documents = build_related_documents(cited_results)
            confidence = _coerce_confidence(
                payload.get("confidence"),
                self._estimate_confidence(retrieval),
            )
        except Exception as exc:
            answer = self._compose_grounded_answer(query, fallback_citations)
            confidence = self._estimate_confidence(retrieval)
            lang = _detect_language(query)
            disclaimer = DISCLAIMER_ID if lang == "id" else DISCLAIMER_EN
            return AnswerResponse(
                query=query,
                answer=answer,
                citations=fallback_citations,
                confidence=confidence,
                related_documents=build_related_documents(selected),
                refusal_reason=None,
                clarification_question=None,
                disclaimer=disclaimer,
                prompt_version_id=self.prompt_template.prompt_version_id,
                retrieved_chunk_ids=retrieved_chunk_ids,
                warnings=[*retrieval.warnings, "groq_answer_fallback_used"],
                debug={
                    "llm_provider": "groq",
                    "llm_model": self.model_name,
                    "fallback_reason": str(exc),
                    "rendered_user_prompt": render_user_prompt(query, retrieval),
                },
            )

        return AnswerResponse(
            query=query,
            answer=answer,
            citations=citations,
            confidence=confidence,
            related_documents=related_documents,
            refusal_reason=None,
            clarification_question=None,
            disclaimer=DISCLAIMER_ID if _detect_language(query) == "id" else DISCLAIMER_EN,
            prompt_version_id=self.prompt_template.prompt_version_id,
            retrieved_chunk_ids=retrieved_chunk_ids,
            warnings=retrieval.warnings,
            debug={
                "llm_provider": "groq",
                "llm_model": self.model_name,
                "rendered_user_prompt": render_user_prompt(query, retrieval),
            },
        )

    def _call_groq(
        self,
        query: str,
        retrieval: RetrievalResponse,
        retrieved_chunk_ids: list[str],
    ) -> dict[str, Any]:
        lang = _detect_language(query)
        lang_instruction = (
            "Tulis answer dalam bahasa Indonesia yang mudah dipindai"
            if lang == "id"
            else "Write the answer in clear, easy-to-scan English"
        )
        user_prompt = "\n\n".join(
            [
                render_user_prompt(query, retrieval),
                "Kembalikan JSON valid saja dengan bentuk:",
                '{"answer":"...","confidence":0.0,"cited_chunk_ids":["..."]}',
                "cited_chunk_ids hanya boleh memakai chunk berikut: "
                + ", ".join(retrieved_chunk_ids),
                (
                    f"{lang_instruction}: awali dengan "
                    "kesimpulan singkat, gunakan paragraf pendek atau daftar bernomor bila "
                    "ada beberapa poin. Jangan tulis chunk ID, citation ID, tanda rujukan "
                    "seperti [chunk-id], atau daftar sumber di dalam answer; sumber akan "
                    "ditampilkan terpisah oleh aplikasi."
                ),
            ]
        )
        completion = self._groq_client().chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.prompt_template.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=self.max_tokens,
        )
        content = completion.choices[0].message.content
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("Groq response JSON is not an object.")
        return payload

    def _groq_client(self):
        if self._client is None:
            try:
                from groq import Groq
            except ImportError as exc:
                raise RuntimeError("groq is required for LLM_PROVIDER=groq.") from exc
            self._client = Groq(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
        return self._client


def _coerce_confidence(value: Any, fallback: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return fallback
    return round(max(0.0, min(confidence, 0.95)), 3)


def _clean_answer_text(answer: str, retrieved_chunk_ids: list[str]) -> str:
    cleaned = answer
    for chunk_id in sorted(retrieved_chunk_ids, key=len, reverse=True):
        escaped_id = re.escape(chunk_id)
        cleaned = re.sub(rf"\[\[\s*{escaped_id}\s*\]\]", "", cleaned)
        cleaned = re.sub(rf"\[\s*{escaped_id}\s*\]", "", cleaned)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()
