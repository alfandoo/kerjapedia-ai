"""Compare a candidate prompt against the active prompt on verified held-out cases."""

from __future__ import annotations

from collections.abc import Callable

from app.services.answering.schemas import PromptTemplate
from app.services.evaluation.policy import RELEASE_QUALITY_GATES
from app.services.evaluation.runner import run_provider_evaluation
from app.services.evaluation.schemas import EvaluationQuestion

REQUIRED_PROMPT_SCENARIOS = frozenset(
    {"follow_up", "bilingual", "hard_negative", "prompt_injection"}
)
HIGHER_IS_BETTER = (
    "citation_precision", "refusal_recall", "refusal_precision", "language_accuracy"
)
LOWER_IS_BETTER = ("unsupported_claim_rate",)


def compare_prompt_versions(
    questions: list[EvaluationQuestion],
    retriever,
    generator_factory: Callable[[PromptTemplate], object],
    baseline: PromptTemplate,
    candidate: PromptTemplate,
    *,
    top_k: int = 10,
) -> dict:
    """Run both templates against the same verified split and report regressions.

    This is a pre-publication check. It does not mutate active prompt state.
    """
    if not questions or any(
        item.status != "verified" or item.verified_by in ("", "unknown")
        for item in questions
    ):
        raise ValueError("Prompt comparison requires human-verified questions.")
    development = [item for item in questions if item.split == "development"]
    held_out = [item for item in questions if item.split == "test"]
    if not development or not held_out:
        raise ValueError("Prompt comparison requires development and held-out test splits.")
    covered = {tag for item in held_out for tag in item.scenario_tags}
    missing = REQUIRED_PROMPT_SCENARIOS - covered
    if missing:
        raise ValueError(f"Held-out prompt scenarios missing: {', '.join(sorted(missing))}")

    baseline_report = run_provider_evaluation(
        questions, retriever, generator_factory(baseline), top_k=top_k
    )
    candidate_report = run_provider_evaluation(
        questions, retriever, generator_factory(candidate), top_k=top_k
    )
    baseline_experiment = baseline_report["experiments"][0]
    candidate_experiment = candidate_report["experiments"][0]
    before = baseline_experiment["metrics"]
    after = candidate_experiment["metrics"]
    tracked = set(HIGHER_IS_BETTER) | set(LOWER_IS_BETTER)
    deltas = {key: after[key] - before[key] for key in sorted(tracked)}
    regressions = [key for key in HIGHER_IS_BETTER if deltas[key] < -1e-9]
    regressions += [key for key in LOWER_IS_BETTER if deltas[key] > 1e-9]
    for key, minimum in RELEASE_QUALITY_GATES.items():
        if after[key] < minimum:
            regressions.append(f"quality_gate:{key}")
    if after["unsupported_claim_rate"] > 0.01:
        regressions.append("quality_gate:unsupported_claim_rate")

    return {
        "baseline_prompt_version_id": baseline.prompt_version_id,
        "candidate_prompt_version_id": candidate.prompt_version_id,
        "held_out_case_count": len(held_out),
        "covered_scenarios": sorted(covered),
        "baseline_metrics": before,
        "candidate_metrics": after,
        "metric_deltas": deltas,
        "baseline_results": baseline_experiment["results"],
        "candidate_results": candidate_experiment["results"],
        "regressions": regressions,
        "passed": not regressions,
    }


def main() -> None:
    """Evaluate a draft prompt against the active version before publishing."""
    import argparse
    import json
    from pathlib import Path

    from app.core.config import settings
    from app.db.session import create_session
    from app.models.business import PromptVersion
    from app.services.evaluation.dataset import load_evaluation_dataset
    from app.services.providers import (
        answer_generator_from_settings,
        reset_provider_caches,
        upstash_vector_store_from_settings,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--candidate-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    _, questions = load_evaluation_dataset(args.dataset)
    with create_session() as session:
        active = session.query(PromptVersion).filter(PromptVersion.status == "active").one()
        candidate = session.get(PromptVersion, args.candidate_version)
        if candidate is None or candidate.status != "draft":
            raise ValueError("Candidate prompt must exist with draft status.")
        baseline_template = PromptTemplate(
            active.version_id, active.system_prompt, active.user_template
        )
        candidate_template = PromptTemplate(
            candidate.version_id, candidate.system_prompt, candidate.user_template
        )

    def make_generator(template: PromptTemplate):
        reset_provider_caches()
        generator = answer_generator_from_settings(settings)
        generator.prompt_template = template
        return generator

    report = compare_prompt_versions(
        questions,
        upstash_vector_store_from_settings(settings),
        make_generator,
        baseline_template,
        candidate_template,
        top_k=args.top_k,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prompt comparison {'passed' if report['passed'] else 'failed'}: {args.output}")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
