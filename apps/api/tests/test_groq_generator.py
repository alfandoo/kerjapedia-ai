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
    assert generator._request_options() == {}


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
