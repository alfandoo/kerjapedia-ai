"""Sample retrieval evaluation: 10 golden questions against Upstash Hybrid.

Deterministic sample: first answerable question per category (9) + the
first refusal question (1). Measures pure ranking (min_final_score=0.0)
with the repository's own metric functions, so numbers stay comparable
with evaluation/BASELINE_REPORT.md conventions.

Usage (from the repository root)::

    apps/api/.venv/Scripts/python scripts/eval_upstash_sample.py
    apps/api/.venv/Scripts/python scripts/eval_upstash_sample.py --top-k 10 --output storage/evaluation/upstash_sample_eval_10.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

DEFAULT_DATASET = REPO_ROOT / "evaluation" / "golden_questions.json"
DEFAULT_OUTPUT = REPO_ROOT / "storage" / "evaluation" / "upstash_sample_eval_10.json"
SAMPLE_CATEGORIES = [
    "alih_daya",
    "bpjs_jkp",
    "hubungan_industrial",
    "k3",
    "pengupahan",
    "phk_pesangon",
    "pkwt",
    "thr",
    "waktu_kerja",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=10)
    return parser


def _normalize_article(value: str) -> str:
    """Normalize article labels: 'Pasal 18' and '18' both become '18'.

    Chunk metadata stores bare numbers while the golden dataset uses the
    'Pasal N' form; compare the numeric core so the metric measures
    retrieval quality instead of label formatting.
    """
    import re

    match = re.search(r"\d+[a-z]?", value.lower())
    return match.group(0) if match else ""


def pick_sample(questions):
    sample = []
    for category in SAMPLE_CATEGORIES:
        match = next(
            (q for q in questions if q.category == category and not q.should_refuse),
            None,
        )
        if match is not None:
            sample.append(match)
    refusal = next((q for q in questions if q.should_refuse), None)
    if refusal is not None:
        sample.append(refusal)
    return sample


def main() -> int:
    args = build_parser().parse_args()

    from app.core.config import settings
    from app.services.evaluation.dataset import load_evaluation_dataset
    from app.services.evaluation.metrics import (
        hit_rate,
        ndcg_at_k,
        precision_at_k,
        recall_at_k,
        reciprocal_rank,
    )
    from app.services.retrieval.upstash_vector_store import (
        UpstashVectorConfig,
        UpstashVectorStore,
    )

    if not settings.upstash_vector_url or not settings.upstash_vector_token:
        print("Missing Upstash credentials.", file=sys.stderr)
        return 2

    _, questions = load_evaluation_dataset(args.dataset)
    sample = pick_sample(questions)
    print(f"Sampled {len(sample)} questions from {args.dataset.name}")

    store = UpstashVectorStore(
        config=UpstashVectorConfig(
            url=settings.upstash_vector_url,
            token=settings.upstash_vector_token,
            dimension=settings.upstash_vector_dimension,
            namespace=settings.upstash_vector_namespace,
        ),
    )

    rows = []
    for question in sample:
        started = time.monotonic()
        response = store.search(question.question, top_k=args.top_k, min_final_score=0.0)
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        retrieved_doc_ids = [item.document.document_id for item in response.results]
        retrieved_articles = [item.document.article or "" for item in response.results]
        if question.should_refuse:
            rows.append(
                {
                    "question_id": question.question_id,
                    "category": question.category,
                    "question": question.question,
                    "should_refuse": True,
                    "refused": response.should_refuse,
                    "latency_ms": latency_ms,
                }
            )
            continue
        expected_articles = [a.lower() for a in question.expected_articles]
        article_hit = any(
            _normalize_article(expected)
            and _normalize_article(expected) == _normalize_article(article or "")
            for expected in expected_articles
            for article in retrieved_articles[:5]
        )
        rows.append(
            {
                "question_id": question.question_id,
                "category": question.category,
                "question": question.question,
                "should_refuse": False,
                "expected_docs": question.expected_document_ids,
                "retrieved_docs_top5": list(dict.fromkeys(retrieved_doc_ids))[:5],
                "recall_at_5": recall_at_k(question.expected_document_ids, retrieved_doc_ids, 5),
                "precision_at_5": precision_at_k(
                    question.expected_document_ids, retrieved_doc_ids, 5
                ),
                "hit_at_5": hit_rate(question.expected_document_ids, retrieved_doc_ids, 5),
                "mrr": reciprocal_rank(question.expected_document_ids, retrieved_doc_ids),
                "ndcg_at_10": ndcg_at_k(
                    question.expected_document_ids, retrieved_doc_ids, 10
                ),
                "article_hit_at_5": article_hit,
                "latency_ms": latency_ms,
            }
        )

    answerable = [row for row in rows if not row["should_refuse"]]
    refusals = [row for row in rows if row["should_refuse"]]
    aggregate = {
        "sample_size": len(rows),
        "answerable": len(answerable),
        "recall_at_5": round(mean([r["recall_at_5"] for r in answerable]), 4)
        if answerable
        else 0.0,
        "precision_at_5": round(mean([r["precision_at_5"] for r in answerable]), 4)
        if answerable
        else 0.0,
        "hit_at_5": round(mean([r["hit_at_5"] for r in answerable]), 4)
        if answerable
        else 0.0,
        "mrr": round(mean([r["mrr"] for r in answerable]), 4) if answerable else 0.0,
        "ndcg_at_10": round(mean([r["ndcg_at_10"] for r in answerable]), 4)
        if answerable
        else 0.0,
        "article_hit_rate_at_5": round(
            mean([1.0 if r["article_hit_at_5"] else 0.0 for r in answerable]), 4
        )
        if answerable
        else 0.0,
        "refusal_correct": sum(1 for r in refusals if r["refused"]),
        "refusal_total": len(refusals),
        "mean_latency_ms": round(mean([r["latency_ms"] for r in rows]), 1) if rows else 0.0,
    }

    print(f"\n{'ID':<22}{'cat':<20}{'R@5':>6}{'P@5':>6}{'Hit':>5}{'MRR':>6}{'nDCG':>6}{'Art':>5}")
    for row in rows:
        if row["should_refuse"]:
            print(
                f"{row['question_id']:<22}{row['category']:<20}"
                f"{'refusal(exp:refuse,got:' + str(row['refused']) + ')':>33}"
            )
            continue
        print(
            f"{row['question_id']:<22}{row['category']:<20}"
            f"{row['recall_at_5']:>6.2f}{row['precision_at_5']:>6.2f}"
            f"{row['hit_at_5']:>5.0f}{row['mrr']:>6.2f}{row['ndcg_at_10']:>6.2f}"
            f"{'Y' if row['article_hit_at_5'] else 'n':>5}"
        )
    print(f"\nAggregate ({aggregate['answerable']} answerable):")
    for key in (
        "recall_at_5",
        "precision_at_5",
        "hit_at_5",
        "mrr",
        "ndcg_at_10",
        "article_hit_rate_at_5",
        "mean_latency_ms",
    ):
        print(f"  {key}={aggregate[key]}")
    print(
        f"  refusal={aggregate['refusal_correct']}/{aggregate['refusal_total']} correct"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"aggregate": aggregate, "rows": rows}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(f"\nReport written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
