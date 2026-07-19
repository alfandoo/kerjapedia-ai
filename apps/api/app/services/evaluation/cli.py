from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.evaluation.dataset import load_evaluation_dataset
from app.services.evaluation.runner import EXPERIMENT_MODES, run_experiments
from app.services.retrieval.store import load_artifact_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KerjaPedia RAG evaluation experiments.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--modes", nargs="+", choices=EXPERIMENT_MODES, default=EXPERIMENT_MODES)
    args = parser.parse_args()

    _, questions = load_evaluation_dataset(args.dataset)
    documents = load_artifact_documents(args.storage_root)
    report = run_experiments(questions, documents, args.modes, args.top_k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote evaluation report to {args.output}")


if __name__ == "__main__":
    main()
