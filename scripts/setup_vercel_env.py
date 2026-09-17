"""Generate Vercel environment variables from .env file.

Usage:
    python scripts/setup_vercel_env.py --env-file .env --api-url https://your-api.up.railway.app

Prints the Vercel CLI commands to set environment variables.
"""

from __future__ import annotations

import argparse
import os
import sys


# Mapping from .env variable names to Vercel env var names and scopes
VERCEL_ENV_MAP = {
    # Web app needs these
    "NEXT_PUBLIC_API_URL": {"scope": "client", "description": "Public API URL for browser requests"},
    "API_INTERNAL_URL": {"scope": "server", "description": "Internal API URL for server-side calls"},
    "APP_ORIGIN": {"scope": "server", "description": "Frontend origin for CSRF checks"},
    "NEXT_PUBLIC_GOOGLE_CLIENT_ID": {"scope": "client", "description": "Google OAuth client ID"},
}


def parse_env_file(path: str) -> dict[str, str]:
    """Parse a .env file into a dict."""
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                env[key] = value
    return env


def main():
    parser = argparse.ArgumentParser(description="Generate Vercel env setup commands")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    parser.add_argument("--api-url", required=True, help="Deployed API URL (e.g., https://api.xxx.up.railway.app)")
    parser.add_argument("--app-origin", help="Vercel app URL (e.g., https://kerjapedia.vercel.app)")
    parser.add_argument("--print-only", action="store_true", help="Only print, don't execute")
    args = parser.parse_args()

    env = parse_env_file(args.env_file)

    print("=" * 60)
    print("Vercel Environment Variables Setup")
    print("=" * 60)
    print()

    # Generate Vercel CLI commands
    vercel_vars = {
        "NEXT_PUBLIC_API_URL": args.api_url,
        "API_INTERNAL_URL": args.api_url,
        "APP_ORIGIN": args.app_origin or args.api_url,
    }

    print("# Run these commands with Vercel CLI:")
    print("# npm i -g vercel")
    print("# vercel link (to your project)")
    print()

    for key, value in vercel_vars.items():
        scope = VERCEL_ENV_MAP.get(key, {}).get("scope", "production")
        print(f'.vercel env add {key} {scope} <<< EOF')
        print(value)
        print("EOF")
        print()

    print("=" * 60)
    print("Or set via Vercel Dashboard:")
    print("=" * 60)
    print()
    for key, value in vercel_vars.items():
        print(f"  {key} = {value}")
    print()

    print("=" * 60)
    print("API-side environment variables (for Railway/Render/Fly.io):")
    print("=" * 60)
    print()
    print("Copy these from your .env file:")
    api_keys = [
        "APP_ENV", "DATABASE_URL", "SUPABASE_URL", "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME",
        "PINECONE_NAMESPACE", "PINECONE_CLOUD", "PINECONE_REGION",
        "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_DIMENSION",
        "EMBEDDING_MODEL_REVISION", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
        "CLAIM_VERIFIER_MODEL", "RERANKER_PROVIDER", "RERANKER_MODEL",
        "REDIS_URL", "CELERY_ENABLED", "RAG_FAIL_CLOSED",
        "RAG_ALLOW_UNPUBLISHED", "ADMIN_EMAIL", "ADMIN_PASSWORD",
        "CORS_ORIGINS", "TELEMETRY_ENABLED", "RAGAS_ENABLED",
    ]
    for key in api_keys:
        value = env.get(key, "<NOT SET>")
        if key in ("ADMIN_PASSWORD", "SUPABASE_SERVICE_ROLE_KEY", "PINECONE_API_KEY", "OPENROUTER_API_KEY"):
            value = "<SECRET>"
        print(f"  {key}={value}")


if __name__ == "__main__":
    main()
