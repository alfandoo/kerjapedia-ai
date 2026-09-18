"""Groq-backed answer generator.

Reuses the full OpenRouter pipeline (grounded prompt, JSON validation,
sentence salvage, extractive fallback, claim verification) but talks to
Groq's OpenAI-compatible endpoint, which serves models such as
``openai/gpt-oss-120b`` with much lower latency than the free OpenRouter
routing used in development.

Only the transport differs: Groq client (own base URL) and no
OpenRouter-specific request options. Set ``verifier_provider="groq"`` to
run LLM claim verification on Groq as well, or ``"deterministic"`` to
skip the verifier call entirely.
"""

from __future__ import annotations

from typing import Any

from app.services.answering.openrouter_generator import OpenRouterAnswerGenerator

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqAnswerGenerator(OpenRouterAnswerGenerator):
    provider_label = "groq"

    def __init__(
        self,
        api_key: str,
        model_name: str = GROQ_DEFAULT_MODEL,
        **kwargs: Any,
    ) -> None:
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is required for LLM_PROVIDER=groq.")
        verifier_provider = kwargs.get("verifier_provider", "deterministic")
        if verifier_provider not in ("groq", "deterministic"):
            raise ValueError(
                "CLAIM_VERIFIER_PROVIDER must be groq or deterministic "
                "when LLM_PROVIDER=groq."
            )
        super().__init__(api_key=api_key, model_name=model_name, **kwargs)

    def _request_options(self) -> dict[str, Any]:
        # Groq has no OpenRouter-style automatic model fallback parameter.
        # reasoning_effort=low keeps the reasoning model from spending its
        # token budget on hidden reasoning and returning empty output
        # (which Groq rejects server-side as json_validate_failed).
        return {"reasoning_effort": "low"}

    def _response_formats_to_try(self) -> list[dict[str, str] | None]:
        # If Groq's server-side JSON validator rejects an empty generation,
        # retry once in plain mode; the shared client-side parser still
        # extracts the first balanced JSON object from prose.
        return [{"type": "json_object"}, None]

    def _openrouter_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("openai is required for LLM_PROVIDER=groq.") from exc
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=GROQ_BASE_URL,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
        return self._client
