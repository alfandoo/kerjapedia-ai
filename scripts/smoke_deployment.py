from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def fetch(url: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "kerjapedia-deployment-smoke/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a KerjaPedia deployment.")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--web-url", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    try:
        api_status, api_body = fetch(f"{args.api_url.rstrip('/')}/health", args.timeout)
        health = json.loads(api_body)
        if api_status != 200 or health.get("status") != "ok":
            raise RuntimeError(f"API health check failed: status={api_status}")

        web_status, web_body = fetch(args.web_url.rstrip("/") + "/", args.timeout)
        if web_status != 200 or b"<html" not in web_body.lower():
            raise RuntimeError(f"Web smoke check failed: status={web_status}")
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise SystemExit(f"Deployment smoke test failed: {exc}") from exc

    print(
        json.dumps(
            {
                "status": "ok",
                "api_url": args.api_url,
                "web_url": args.web_url,
                "api_version": health.get("version"),
            }
        )
    )


if __name__ == "__main__":
    main()
