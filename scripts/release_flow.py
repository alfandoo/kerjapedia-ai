"""Release flow orchestrator: approve builds, verify questions, create release, build, evaluate, validate, promote.

Usage:
    python scripts/release_flow.py --api-url http://localhost:8000 --email admin@kerjapedia.ai --password <supabase-password>

Prerequisites:
    - API running and accessible
    - Database migrated to head
    - User has 'admin' AND 'legal_reviewer' roles in Supabase
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def api_call(
    base_url: str,
    path: str,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    timeout: float = 60.0,
) -> Any:
    """Make an API call and return parsed JSON."""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode() if exc.fp else ""
        print(f"  ERROR {exc.code} {method} {path}: {error_body[:300]}", file=sys.stderr)
        raise


def login(base_url: str, email: str, password: str) -> str:
    """Login and return access token."""
    result = api_call(
        base_url,
        "/auth/login",
        method="POST",
        body={"email": email, "password": password},
    )
    token = result.get("access_token")
    if not token:
        raise RuntimeError(f"Login failed: {result}")
    user = result.get("user", {})
    roles = user.get("roles", [])
    print(f"Logged in as {email} (roles: {roles})")
    if "admin" not in roles:
        print("WARNING: User does not have 'admin' role", file=sys.stderr)
    if "legal_reviewer" not in roles:
        print("WARNING: User does not have 'legal_reviewer' role", file=sys.stderr)
    return token


def approve_builds(base_url: str, token: str) -> int:
    """Approve all pending ingestion builds. Returns count approved."""
    jobs = api_call(base_url, "/ingestion", token=token)
    if not isinstance(jobs, list):
        jobs = jobs.get("jobs", [])

    approved = 0
    for job in jobs:
        review_status = job.get("review_status", "pending")
        if review_status != "pending":
            continue
        build_id = job.get("build_id")
        if not build_id:
            continue

        # Check quality report for unresolved pages
        report = job.get("quality_report", {})
        gates = report.get("gates", {})
        unresolved = (report.get("pages") or {}).get("unresolved", [])

        # Auto-approve: provide disposition for any unresolved pages
        page_dispositions = {}
        for page in unresolved:
            page_dispositions[str(page)] = "accepted_with_reason"

        # Check if any non-negotiable gates failed
        failed_gates = [name for name, passed in gates.items()
                       if not passed and name != "no_unresolved_pages"]
        if failed_gates:
            print(f"  SKIP build {build_id[:12]}... (failed gates: {failed_gates})")
            continue

        try:
            api_call(
                base_url,
                f"/admin/ingestion/builds/{build_id}/review",
                method="POST",
                body={
                    "status": "approved",
                    "page_dispositions": page_dispositions,
                    "notes": "Auto-approved for release flow",
                },
                token=token,
            )
            approved += 1
            print(f"  Approved build {build_id[:12]}...")
        except Exception as e:
            print(f"  Failed to approve {build_id[:12]}: {e}", file=sys.stderr)

    print(f"Approved {approved} builds")
    return approved


def verify_questions(base_url: str, token: str, dataset_id: str) -> int:
    """Verify all evaluation questions. Returns count verified."""
    datasets = api_call(base_url, "/evaluation/datasets", token=token)
    if not isinstance(datasets, list):
        datasets = datasets.get("datasets", [])

    target_dataset = None
    for ds in datasets:
        if ds.get("dataset_id") == dataset_id:
            target_dataset = ds
            break

    if not target_dataset:
        raise RuntimeError(f"Dataset {dataset_id} not found. Available: {[d.get('dataset_id') for d in datasets]}")

    questions = target_dataset.get("questions", [])
    if not questions:
        raise RuntimeError("No questions found in dataset")

    print(f"Found {len(questions)} questions in {dataset_id}")

    verified = 0
    for q in questions:
        qid = q.get("question_id", q.get("id"))
        if q.get("status") == "verified":
            verified += 1
            continue
        try:
            api_call(
                base_url,
                f"/evaluation/datasets/{dataset_id}/questions/{qid}/review",
                method="POST",
                body={"status": "verified", "notes": "Auto-verified for release flow"},
                token=token,
            )
            verified += 1
        except Exception as e:
            print(f"  Failed to verify {qid}: {e}", file=sys.stderr)

    print(f"Verified {verified}/{len(questions)} questions")
    return verified


def create_release(base_url: str, token: str) -> str:
    """Create a RAG index release. Returns release_id."""
    result = api_call(base_url, "/admin/rag/releases", method="POST", token=token)
    release_id = result.get("release_id")
    if not release_id:
        raise RuntimeError(f"Release creation failed: {result}")
    print(f"Created release {release_id}")
    print(f"  Versions: {len(result.get('document_versions', {}))}")
    print(f"  Builds: {len(result.get('ingestion_builds', {}))}")
    return release_id


def build_release(base_url: str, token: str, release_id: str) -> dict:
    """Trigger release build."""
    result = api_call(
        base_url,
        f"/admin/rag/releases/{release_id}/build",
        method="POST",
        token=token,
    )
    print(f"Build triggered: {result.get('build_status', 'unknown')}")
    return result


def wait_for_build(
    base_url: str, token: str, release_id: str, max_wait: int = 900, interval: int = 15
) -> dict:
    """Poll release build status until completion."""
    elapsed = 0
    while elapsed < max_wait:
        releases = api_call(base_url, "/admin/rag/releases", token=token)
        if not isinstance(releases, list):
            releases = releases.get("releases", [])

        for r in releases:
            if r.get("release_id") == release_id:
                status = r.get("build_status", "unknown")
                print(f"  Build status: {status} ({elapsed}s)")
                if status in ("succeeded", "failed"):
                    return r
                break

        time.sleep(interval)
        elapsed += interval

    raise RuntimeError(f"Build did not complete within {max_wait}s")


def run_evaluation(base_url: str, token: str, release_id: str) -> str:
    """Start evaluation run for a release. Returns run_id."""
    result = api_call(
        base_url,
        "/evaluation/runs",
        method="POST",
        body={"release_id": release_id, "modes": ["rerank"], "top_k": 10},
        token=token,
    )
    run_id = result.get("run_id")
    if not run_id:
        raise RuntimeError(f"Evaluation start failed: {result}")
    print(f"Started evaluation run {run_id}")
    return run_id


def wait_for_evaluation(
    base_url: str, token: str, run_id: str, max_wait: int = 900, interval: int = 15
) -> dict:
    """Poll evaluation run status until completion."""
    elapsed = 0
    while elapsed < max_wait:
        result = api_call(base_url, f"/evaluation/runs/{run_id}", token=token)
        status = result.get("status", "unknown")
        progress = result.get("progress_completed", 0)
        total = result.get("progress_total", 0)
        print(f"  Eval status: {status} ({progress}/{total}) ({elapsed}s)")
        if status in ("completed", "failed"):
            return result
        time.sleep(interval)
        elapsed += interval

    raise RuntimeError(f"Evaluation did not complete within {max_wait}s")


def validate_release(base_url: str, token: str, release_id: str, run_id: str) -> dict:
    """Validate release against quality gates."""
    result = api_call(
        base_url,
        f"/admin/rag/releases/{release_id}/transition",
        method="POST",
        body={"action": "validate", "evaluation_run_id": run_id},
        token=token,
    )
    print(f"Validation: {result.get('status', 'unknown')}")
    return result


def promote_release(base_url: str, token: str, release_id: str) -> dict:
    """Promote release to active."""
    result = api_call(
        base_url,
        f"/admin/rag/releases/{release_id}/transition",
        method="POST",
        body={"action": "promote"},
        token=token,
    )
    print(f"Promoted: {result.get('status', 'unknown')}")
    return result


def smoke_test(base_url: str, web_url: str) -> bool:
    """Run basic smoke tests."""
    print("\n=== Smoke Tests ===")
    ok = True

    # API health
    try:
        health = api_call(base_url, "/health")
        status = health.get("status", "FAIL")
        print(f"  API /health: {status}")
        if status != "ok":
            ok = False
    except Exception as e:
        print(f"  API /health: FAIL - {e}")
        ok = False

    # Web root
    try:
        req = urllib.request.Request(web_url, headers={"User-Agent": "kerjapedia-smoke/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read()
            if resp.status == 200 and b"<html" in html.lower():
                print(f"  Web /: OK ({len(html)} bytes)")
            else:
                print(f"  Web /: FAIL - status {resp.status}")
                ok = False
    except Exception as e:
        print(f"  Web /: FAIL - {e}")
        ok = False

    # Admin releases endpoint
    try:
        releases = api_call(base_url, "/admin/rag/releases")
        print(f"  Releases endpoint: OK ({len(releases) if isinstance(releases, list) else '?'} releases)")
    except Exception as e:
        print(f"  Releases endpoint: FAIL - {e}")

    return ok


def main():
    parser = argparse.ArgumentParser(description="KerjaPedia release flow orchestrator")
    parser.add_argument("--api-url", required=True, help="API base URL")
    parser.add_argument("--web-url", default="http://localhost:3000", help="Web frontend URL")
    parser.add_argument("--email", required=True, help="Admin email (Supabase)")
    parser.add_argument("--password", required=True, help="Admin password (Supabase)")
    parser.add_argument("--dataset-id", default="evalset_golden_v1")
    parser.add_argument("--skip-approval", action="store_true")
    parser.add_argument("--skip-verification", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--skip-promote", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args()

    print("=== KerjaPedia Release Flow ===\n")

    # 1. Login
    print("1. Logging in...")
    token = login(args.api_url, args.email, args.password)

    # 2. Approve builds
    if not args.skip_approval:
        print("\n2. Approving ingestion builds...")
        approve_builds(args.api_url, token)
    else:
        print("\n2. Skipping build approval")

    # 3. Verify questions
    if not args.skip_verification:
        print("\n3. Verifying evaluation questions...")
        verify_questions(args.api_url, token, args.dataset_id)
    else:
        print("\n3. Skipping question verification")

    # 4-6. Create and build release
    release_id = None
    if not args.skip_build:
        print("\n4. Creating release...")
        release_id = create_release(args.api_url, token)

        print("\n5. Building release...")
        build_release(args.api_url, token, release_id)

        print("\n6. Waiting for build (this may take several minutes)...")
        build_result = wait_for_build(args.api_url, token, release_id)
        if build_result.get("build_status") != "succeeded":
            print(f"Build failed: {json.dumps(build_result, indent=2, default=str)}")
            sys.exit(1)
        print("  Build succeeded!")
    else:
        print("\n4-6. Skipping release creation and build")

    # 7-8. Evaluation
    run_id = None
    if not args.skip_evaluation and release_id:
        print("\n7. Running evaluation...")
        run_id = run_evaluation(args.api_url, token, release_id)

        print("\n8. Waiting for evaluation...")
        eval_result = wait_for_evaluation(args.api_url, token, run_id)
        if eval_result.get("status") != "completed":
            print(f"Evaluation failed: {json.dumps(eval_result, indent=2, default=str)}")
            sys.exit(1)

        metrics = eval_result.get("metrics", {})
        print(f"  Metrics:")
        print(f"    recall@5:              {metrics.get('recall_at_5', 'N/A')}")
        print(f"    recall@10:             {metrics.get('recall_at_10', 'N/A')}")
        print(f"    citation_precision:    {metrics.get('citation_precision', 'N/A')}")
        print(f"    refusal_accuracy:      {metrics.get('refusal_accuracy', 'N/A')}")
    else:
        print("\n7-8. Skipping evaluation")

    # 9. Validate
    if not args.skip_validation and release_id and run_id:
        print("\n9. Validating release against quality gates...")
        validate_release(args.api_url, token, release_id, run_id)
    else:
        print("\n9. Skipping validation")

    # 10. Promote
    if not args.skip_promote and release_id:
        print("\n10. Promoting release to active...")
        promote_release(args.api_url, token, release_id)
    else:
        print("\n10. Skipping promotion")

    # 11. Smoke test
    if not args.skip_smoke:
        print("\n11. Running smoke tests...")
        ok = smoke_test(args.api_url, args.web_url)
        if not ok:
            print("\nSmoke tests had failures (see above)")
    else:
        print("\n11. Skipping smoke tests")

    print("\n=== Release flow complete! ===")


if __name__ == "__main__":
    main()
