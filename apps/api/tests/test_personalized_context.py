from app.services.answering.personalized_context import build_personalized_context


def test_explicit_question_facts_override_saved_profile() -> None:
    context = build_personalized_context(
        "Saya bekerja di Jawa Tengah sejak 2025-01-01. Berapa THR saya?",
        {
            "province": "Jawa Barat",
            "employment_status": "PKWT",
            "start_date": "2024-01-01",
            "monthly_wage": 5000000,
        },
    )
    assert context.facts["province"] == "Jawa Tengah"
    assert context.facts["start_date"] == "2025-01-01"
    assert context.facts["employment_status"] == "PKWT"
    assert "PKWT" in context.retrieval_hint
    assert "Jawa Tengah" not in context.retrieval_hint
    assert "5000000" not in context.retrieval_hint


def test_profile_fact_validation_and_mode_default() -> None:
    from pydantic import ValidationError

    from app.api.schemas import AskRequest, WorkProfileUpdateRequest

    assert AskRequest(question="Berapa THR?").personalized_mode is None
    assert WorkProfileUpdateRequest(province="Jawa Barat").province == "Jawa Barat"
    try:
        WorkProfileUpdateRequest(province="Atlantis")
    except ValidationError:
        pass
    else:
        raise AssertionError("Unknown province should be rejected")


def test_personalized_retrieval_adds_only_non_salary_facts() -> None:
    from app.api.routes_chat import _apply_personalized_retrieval
    from app.services.answering.memory_hardening import MemoryContext

    memory = MemoryContext(
        original_question="Berapa THR saya?", retrieval_query="THR", used=False, source_turns=0
    )
    context = build_personalized_context(
        "Berapa THR saya?",
        {"province": "Jawa Barat", "employment_status": "PKWT", "monthly_wage": 5000000},
    )
    updated = _apply_personalized_retrieval(memory, context)
    assert "Jawa Barat" not in updated.retrieval_query
    assert "PKWT" in updated.retrieval_query
    assert "5000000" not in updated.retrieval_query
    assert memory.retrieval_query == "THR"


def test_profile_facts_are_separate_from_legal_evidence() -> None:
    from app.services.answering.prompts import render_user_prompt_with_budget
    from app.services.retrieval.schemas import RetrievalResponse

    context = build_personalized_context(
        "Berapa THR saya?",
        {"employment_status": "PKWT", "monthly_wage": 5000000},
    )
    retrieval = RetrievalResponse(
        query=None, results=[], warnings=[], should_refuse=False, refusal_reason=None
    )
    prompt, usage = render_user_prompt_with_budget(
        "Berapa THR saya?", retrieval, personalized_context=context.prompt_block
    )
    assert "Fakta kasus yang diberikan pengguna" in prompt
    assert "Upah bulanan (Rp): 5000000" in prompt
    assert "Konteks terpilih (sumber hukum" in prompt
    assert usage["query_tokens"] > 0
    plain, _ = render_user_prompt_with_budget("Berapa THR saya?", retrieval)
    assert "Upah bulanan" not in plain


def test_province_rerank_keeps_national_source() -> None:
    from dataclasses import replace
    from types import SimpleNamespace

    from app.api.routes_chat import _rerank_personalized
    from app.services.retrieval.schemas import RetrievalResponse

    national = SimpleNamespace(
        final_score=0.80, document=SimpleNamespace(metadata={"title": "Peraturan Nasional"})
    )
    local = SimpleNamespace(
        final_score=0.79, document=SimpleNamespace(metadata={"province": "Jawa Barat"})
    )
    original = RetrievalResponse(
        query=None, results=[national, local], warnings=[], should_refuse=False, refusal_reason=None
    )
    context = build_personalized_context("Berapa UMP?", {"province": "Jawa Barat"})
    updated = _rerank_personalized(original, context, 2)
    assert updated.results == [local, national]
    assert original.results == [national, local]
    assert _rerank_personalized(replace(original, results=[national]), context, 2).results == [
        national
    ]


def test_nonstream_generator_does_not_mutate_shared_provider(monkeypatch) -> None:
    from app.api import routes_chat

    class SharedGenerator:
        personalized_context = ""

        def generate(self, question, retrieval, *, history):
            return self.personalized_context

    shared = SharedGenerator()
    monkeypatch.setattr(
        routes_chat, "answer_generator_from_settings", lambda *args, **kwargs: shared
    )
    context = build_personalized_context(
        "Berapa THR?", {"employment_status": "PKWT", "monthly_wage": 5000000}
    )
    result = routes_chat._generate_with_fresh_generator(
        "Berapa THR?", None, (), "standard", 100, 1000, context
    )
    assert "5000000" in result
    assert shared.personalized_context == ""
