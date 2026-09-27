"""Regressions for versioned prompts and provider output contracts."""

from __future__ import annotations

from app.services.answering.groq_generator import GroqAnswerGenerator
from app.services.answering.openrouter_generator import OpenRouterAnswerGenerator
from app.services.answering.prompts import render_user_prompt_with_budget
from app.services.answering.schemas import PromptTemplate
from app.services.retrieval.token_budget import TokenBudget, count_tokens


def test_active_template_is_rendered_and_counted() -> None:
    from test_industrial_rag_providers import retrieval_response

    template = PromptTemplate(
        prompt_version_id="candidate",
        system_prompt="SYSTEM " * 100,
        user_template="QUESTION={query}\nHISTORY={history_block}\nEVIDENCE={context}",
    )
    prompt, usage = render_user_prompt_with_budget(
        "Apa hak pekerja?",
        retrieval_response(),
        budget=TokenBudget(model_window=4000, reserved_output_tokens=500),
        template=template,
    )
    assert prompt.startswith("QUESTION=Apa hak pekerja?\nHISTORY=\nEVIDENCE=")
    assert usage["system_tokens"] == count_tokens(template.system_prompt)
    assert usage["total_prompt_tokens"] == (
        count_tokens(template.system_prompt) + count_tokens(prompt)
    )


def test_answer_format_prefers_strict_schema_with_provider_fallback() -> None:
    for generator in (
        OpenRouterAnswerGenerator(api_key="test-key"),
        GroqAnswerGenerator(api_key="test-key"),
    ):
        formats = generator._response_formats_to_try()
        assert formats[0]["type"] == "json_schema"
        schema = formats[0]["json_schema"]
        assert schema["strict"] is True
        assert set(schema["schema"]["required"]) == {
            "answer", "cited_chunk_ids", "claims"
        }
        assert formats[1] == {"type": "json_object"}
    assert GroqAnswerGenerator(api_key="test-key")._response_formats_to_try()[-1] is None


def test_prompt_comparison_uses_verified_held_out_cases(monkeypatch) -> None:
    from app.services.evaluation import prompt_comparison
    from app.services.evaluation.schemas import EvaluationQuestion

    def question(identifier: str, split: str, tags: list[str]) -> EvaluationQuestion:
        return EvaluationQuestion(
            question_id=identifier,
            category="pkwt",
            question="Apa hak pekerja?",
            expected_answer="Kompensasi.",
            expected_document_ids=["PP-35-2021"],
            expected_articles=["Pasal 15"],
            expected_topics=["pkwt"],
            should_refuse=False,
            verified_by="legal-reviewer",
            status="verified",
            split=split,
            scenario_tags=tags,
        )

    cases = [
        question("dev", "development", []),
        question(
            "held-out", "test",
            ["follow_up", "bilingual", "hard_negative", "prompt_injection", "complex"],
        ),
    ]
    calls = []

    def fake_run(questions, retriever, generator, **kwargs):
        calls.append(generator.prompt_template.prompt_version_id)
        precision = 0.97 if len(calls) == 1 else 0.98
        return {
            "experiments": [{
                "metrics": {
                    "citation_precision": precision,
                    "refusal_recall": 1.0,
                    "refusal_precision": 1.0,
                    "language_accuracy": 1.0,
                    "unsupported_claim_rate": 0.0,
                    "recall_at_5": 1.0,
                    "recall_at_10": 1.0,
                },
                "results": [{"question_id": "held-out", "refusal_correct": True}],
            }],
        }

    monkeypatch.setattr(prompt_comparison, "run_provider_evaluation", fake_run)
    baseline = PromptTemplate("baseline", "system", "{query} {history_block} {context}")
    candidate = PromptTemplate("candidate", "system", "{query} {history_block} {context}")

    class FakeGenerator:
        def __init__(self, template):
            self.prompt_template = template

    report = prompt_comparison.compare_prompt_versions(
        cases, object(), FakeGenerator, baseline, candidate
    )
    assert calls == ["baseline", "candidate"]
    assert report["passed"] is True
    assert report["metric_deltas"]["citation_precision"] > 0
    assert report["held_out_case_count"] == 1

    calls.clear()
    def regressing_run(questions, retriever, generator, **kwargs):
        result = fake_run(questions, retriever, generator, **kwargs)
        if len(calls) == 2:
            result["experiments"][0]["metrics"]["citation_precision"] = 0.94
        return result
    monkeypatch.setattr(prompt_comparison, "run_provider_evaluation", regressing_run)
    regressing = prompt_comparison.compare_prompt_versions(
        cases, object(), FakeGenerator, baseline, candidate
    )
    assert regressing["passed"] is False
    assert "citation_precision" in regressing["regressions"]

    unverified = [cases[0], question("bad", "test", cases[1].scenario_tags)]
    unverified[1] = EvaluationQuestion(**{
        **unverified[1].__dict__, "status": "needs_human_review"
    })
    import pytest
    with pytest.raises(ValueError, match="verified"):
        prompt_comparison.compare_prompt_versions(
            unverified, object(), FakeGenerator, baseline, candidate
        )


def test_groq_streaming_skips_unsupported_strict_schema() -> None:
    generator = GroqAnswerGenerator(api_key="test-key")
    generator.token_budget = 5000
    assert generator._response_formats_to_try() == [{"type": "json_object"}, None]


def test_active_template_reaches_provider_request() -> None:
    from test_industrial_rag_providers import FakeOpenRouterClient, retrieval_response

    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator.prompt_template = PromptTemplate(
        "candidate", "CUSTOM SYSTEM", "CUSTOM QUESTION: {query}\n{history_block}{context}"
    )
    generator._client = FakeOpenRouterClient({
        "answer": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
        "cited_chunk_ids": ["chunk-1"],
        "claims": [{
            "text": "Pekerja PKWT memperoleh kompensasi berdasarkan Pasal 15.",
            "cited_chunk_ids": ["chunk-1"],
        }],
    })
    generator.generate("Apakah pekerja PKWT memperoleh kompensasi?", retrieval_response())
    messages = generator._client.requests[0]["messages"]
    assert messages[0]["content"] == "CUSTOM SYSTEM"
    assert messages[1]["content"].startswith("CUSTOM QUESTION:")
    assert generator._client.requests[0]["response_format"]["type"] == "json_schema"


def test_schema_rejection_falls_back_to_json_mode() -> None:
    from types import SimpleNamespace

    class UnsupportedFormat(Exception):
        status_code = 400

    class FakeCompletions:
        def __init__(self):
            self.formats = []

        def create(self, **kwargs):
            self.formats.append(kwargs["response_format"]["type"])
            if len(self.formats) == 1:
                raise UnsupportedFormat("response_format json_schema is unsupported")
            return SimpleNamespace(choices=[])

    completions = FakeCompletions()
    generator = OpenRouterAnswerGenerator(api_key="test-key")
    generator._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    generator._create_completion(
        model="test-model", messages=[{"role": "user", "content": "test"}],
        temperature=0, max_tokens=100,
    )
    assert completions.formats == ["json_schema", "json_object"]
