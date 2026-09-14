from __future__ import annotations

from app.core.config import Settings


def build_ragas_faithfulness(settings: Settings):
    try:
        from openai import OpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import Faithfulness
    except ImportError as exc:
        raise RuntimeError("Ragas and OpenRouter are required for secondary evaluation.") from exc
    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    evaluator = llm_factory(
        settings.claim_verifier_model,
        provider="openai",
        client=client,
    )
    return Faithfulness(llm=evaluator)


def score_ragas_faithfulness(
    scorer,
    *,
    question: str,
    response: str,
    contexts: list[str],
) -> float:
    result = scorer.score(
        user_input=question,
        response=response,
        retrieved_contexts=contexts,
    )
    return round(float(result.value), 6)
