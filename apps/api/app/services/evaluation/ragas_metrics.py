from __future__ import annotations

from app.core.config import Settings


def build_ragas_faithfulness(settings: Settings):
    try:
        from groq import Groq
        from ragas.llms import llm_factory
        from ragas.metrics.collections import Faithfulness
    except ImportError as exc:
        raise RuntimeError("Ragas and Groq are required for secondary evaluation.") from exc
    client = Groq(
        api_key=settings.groq_api_key,
        timeout=settings.groq_timeout_seconds,
        max_retries=settings.groq_max_retries,
    )
    evaluator = llm_factory(
        settings.claim_verifier_model,
        provider="groq",
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
