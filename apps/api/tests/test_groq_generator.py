"""Groq answer generator tests (provider API is mocked)."""

from __future__ import annotations

import sys
import types

import pytest

from app.services.answering.groq_generator import (
    GROQ_BASE_URL,
    GROQ_DEFAULT_MODEL,
    GroqAnswerGenerator,
)
from app.services.answering.openrouter_generator import OpenRouterAnswerGenerator


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch, calls: dict) -> None:
    fake_module = types.ModuleType("openai")

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            calls.update(kwargs)

    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def test_provider_labels() -> None:
    assert GroqAnswerGenerator.provider_label == "groq"
    assert OpenRouterAnswerGenerator.provider_label == "openrouter"
    assert GROQ_DEFAULT_MODEL == "openai/gpt-oss-120b"


def test_missing_api_key_raises() -> None:
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        GroqAnswerGenerator(api_key="")


def test_mismatched_verifier_provider_raises() -> None:
    with pytest.raises(ValueError, match="CLAIM_VERIFIER_PROVIDER"):
        GroqAnswerGenerator(api_key="test-key", verifier_provider="openrouter")


def test_client_uses_groq_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_openai(monkeypatch, calls)
    generator = GroqAnswerGenerator(api_key="test-key")
    generator._openrouter_client()
    assert calls["base_url"] == GROQ_BASE_URL
    assert calls["api_key"] == "test-key"
    assert generator._request_options() == {"reasoning_effort": "low"}
    assert generator._response_formats_to_try() == [{"type": "json_object"}, None]


def test_json_validate_failed_falls_back_to_plain_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.answering import openrouter_generator as parent

    assert parent.OpenRouterAnswerGenerator._response_formats_to_try(
        GroqAnswerGenerator(api_key="test-key")
    ) == [{"type": "json_object"}]

    calls: dict = {"attempts": []}

    class FlakyCompletions:
        def create(self, **kwargs):
            calls["attempts"].append(kwargs)
            if len(calls["attempts"]) == 1:
                raise RuntimeError("json_validate_failed: empty failed_generation")
            return "plain-mode-completion"

    class FakeClient:
        chat = types.SimpleNamespace(completions=FlakyCompletions())

    generator = GroqAnswerGenerator(api_key="test-key")
    generator._client = FakeClient()
    result = generator._create_completion(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=600,
    )
    assert result == "plain-mode-completion"
    assert calls["attempts"][0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls["attempts"][1]


def test_factory_builds_groq_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.services import providers

    calls: dict = {}
    _install_fake_openai(monkeypatch, calls)
    monkeypatch.setattr(settings, "llm_provider", "groq", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "claim_verifier_provider", "deterministic", raising=False)
    providers.reset_provider_caches()
    try:
        generator = providers.answer_generator_from_settings(settings)
    finally:
        providers.reset_provider_caches()
    assert isinstance(generator, GroqAnswerGenerator)


def test_factory_requires_groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.services import providers

    monkeypatch.setattr(settings, "llm_provider", "groq", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", None, raising=False)
    providers.reset_provider_caches()
    try:
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            providers.answer_generator_from_settings(settings)
    finally:
        providers.reset_provider_caches()


def _empty_retrieval():
    from app.services.retrieval.query import understand_query
    from app.services.retrieval.schemas import RetrievalResponse

    return RetrievalResponse(
        query=understand_query("Apakah pekerja PKWT memperoleh kompensasi?"),
        results=[],
        warnings=[],
        should_refuse=False,
        refusal_reason=None,
    )


def test_rate_limit_returns_dedicated_notice() -> None:
    from app.services.answering.openrouter_generator import RATE_LIMITED_WARNING

    generator = GroqAnswerGenerator(api_key="test-key")
    response = generator._temporarily_unavailable_response(
        query="Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval=_empty_retrieval(),
        selected=[],
        citations=[],
        retrieved_chunk_ids=[],
        token_usage={},
        failure_category="provider_failure",
        validation_issues=[],
        provider_failure_type="RateLimitError",
        generation_attempts=3,
    )
    assert "batas pemakaian" in response.answer
    assert RATE_LIMITED_WARNING in response.warnings


def test_non_rate_limit_keeps_generic_notice() -> None:
    from app.services.answering.openrouter_generator import RATE_LIMITED_WARNING

    generator = GroqAnswerGenerator(api_key="test-key")
    response = generator._temporarily_unavailable_response(
        query="Apakah pekerja PKWT memperoleh kompensasi?",
        retrieval=_empty_retrieval(),
        selected=[],
        citations=[],
        retrieved_chunk_ids=[],
        token_usage={},
        failure_category="provider_failure",
        validation_issues=[],
        provider_failure_type="APIConnectionError",
        generation_attempts=3,
    )
    assert "batas pemakaian" not in response.answer
    assert RATE_LIMITED_WARNING not in response.warnings
