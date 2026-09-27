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
    assert generator._request_options() == {
        "reasoning_effort": "medium",
        "extra_body": {"include_reasoning": False},
    }
    assert [fmt["type"] if fmt else None for fmt in generator._response_formats_to_try()] == [
        "json_schema", "json_object", None
    ]


def test_reasoning_effort_is_configurable_and_hidden() -> None:
    generator = GroqAnswerGenerator(api_key="test-key", reasoning_effort="high")

    assert generator._request_options() == {
        "reasoning_effort": "high",
        "extra_body": {"include_reasoning": False},
    }


def test_json_validate_failed_falls_back_to_plain_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.answering import openrouter_generator as parent

    assert [
        fmt["type"] for fmt in parent.OpenRouterAnswerGenerator._response_formats_to_try(
            GroqAnswerGenerator(api_key="test-key")
        )
    ] == ["json_schema", "json_object"]

    calls: dict = {"attempts": []}

    class FlakyCompletions:
        def create(self, **kwargs):
            calls["attempts"].append(kwargs)
            if len(calls["attempts"]) <= 2:
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
    assert calls["attempts"][0]["response_format"]["type"] == "json_schema"
    assert calls["attempts"][1]["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls["attempts"][2]


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
    assert generator.reasoning_effort == "medium"


def test_factory_caches_each_reasoning_mode_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.services import providers

    monkeypatch.setattr(settings, "llm_provider", "groq", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "claim_verifier_provider", "deterministic", raising=False)
    providers.reset_provider_caches()
    try:
        fast = providers.answer_generator_from_settings(settings, reasoning_mode="fast")
        deep = providers.answer_generator_from_settings(settings, reasoning_mode="deep")
        fast_again = providers.answer_generator_from_settings(settings, reasoning_mode="fast")
    finally:
        providers.reset_provider_caches()

    assert fast.reasoning_effort == "low"
    assert deep.reasoning_effort == "high"
    assert fast is fast_again
    assert fast is not deep


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


def test_stream_quota_stops_generation_and_reports_usage():
    import asyncio
    from types import SimpleNamespace

    from app.services.answering.openrouter_generator import (
        OpenRouterAnswerGenerator,
        ProcessingQuotaExhausted,
    )
    from app.services.answering.provider_cancellation import (
        ProviderRequestScope,
        current_provider_scope,
    )

    class FakeStream:
        def __init__(self):
            self.closed = False
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.index += 1
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="jawaban " * 20), finish_reason=None
                    )
                ],
                usage=None,
            )

        async def close(self):
            self.closed = True

    async def run():
        stream = FakeStream()
        generator = OpenRouterAnswerGenerator(api_key="test")
        generator.token_budget = 500

        async def fake_create(_kwargs):
            return stream

        generator._async_open_stream = fake_create
        scope = ProviderRequestScope(asyncio.get_running_loop())
        token = current_provider_scope.set(scope)
        try:
            with pytest.raises(ProcessingQuotaExhausted):
                await asyncio.to_thread(
                    generator._create_completion,
                    model="test",
                    messages=[{"role": "user", "content": "question"}],
                    temperature=0,
                    max_tokens=300,
                )
        finally:
            current_provider_scope.reset(token)
        assert stream.closed
        assert scope.usage["completion_tokens"] > 0

    asyncio.run(run())
