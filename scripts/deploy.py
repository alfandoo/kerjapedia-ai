"""Deployment helper script for Render (API) + Vercel (Web).

Usage:
    python scripts/deploy.py --help
    python scripts/deploy.py setup-render
    python scripts/deploy.py setup-vercel
    python scripts/deploy.py test-api <api_url>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def api_call(
    url: str,
    method: str = "GET",
    body: dict | None = None,
    timeout: float = 30.0,
) -> dict:
    """Make an HTTP call and return parsed JSON."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()) if resp.read() else {}
    except urllib.error.HTTPError as e:
        print(f"ERROR {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
        raise


def setup_render():
    """Print Render deployment instructions."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                  DEPLOY TO RENDER (API)                     ║
╚══════════════════════════════════════════════════════════════╝

1. LOGIN TO RENDER
   → Go to https://dashboard.render.com
   → Sign up with GitHub (no credit card needed)

2. CREATE NEW BLUEPRINT
   → Click "New" → "Blueprint"
   → Connect your GitHub repo: alfandoo/kerjapedia-ai
   → Render will detect render.yaml automatically

3. SET ENVIRONMENT VARIABLES
   → In Render Dashboard, go to your service → "Environment"
   → Add these SECRET variables (click "Add Environment Variable"):

   Required:
   • SUPABASE_URL = https://ybfhmxjldxfdlxpfviuk.supabase.co
   • SUPABASE_SERVICE_KEY = (your supabase service key from .env)
   • SUPABASE_ANON_KEY = (your supabase anon key from .env)
   • DATABASE_URL = (your database URL from .env)
   • REDIS_URL = (your Upstash Redis URL from .env)
   • OPENROUTER_API_KEY = (your OpenRouter API key from .env)
   • PINECONE_API_KEY = (your Pinecone API key from .env)
   • SMTP_USERNAME = kerjapedia@zohomail.com
   • SMTP_PASSWORD = (your SMTP password from .env)
   • SMTP_SENDER_EMAIL = kerjapedia@zohomail.com

4. DEPLOY
   → Render will auto-deploy from the Blueprint
   → First deploy takes ~5-10 min (downloading BGE-M3 model)
   → Your API URL will be: https://kerjapedia-api.onrender.com

5. RUN DATABASE MIGRATION
   → In Render Dashboard, go to your service → "Shell"
   → Run: python -m alembic upgrade head

6. VERIFY
   → Open: https://kerjapedia-api.onrender.com/health
   → Should return: {"status": "ok"}
""")


def setup_vercel():
    """Print Vercel deployment instructions."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                 DEPLOY TO VERCEL (WEB)                      ║
╚══════════════════════════════════════════════════════════════╝

PREREQUISITE: Deploy API to Render first and get the API URL.

1. LOGIN TO VERCEL
   → Open terminal
   → Run: vercel login
   → Follow GitHub login flow

2. INITIALIZE VERCEL PROJECT
   → In the project root (KerjaPediaAI), run:
   → Run: vercel

   When prompted:
   • Set up and deploy? → Y
   • Which scope? → (your account)
   • Link to existing project? → N
   • Project name? → kerjapedia-web
   • Directory where code is located? → apps/web
   • Want to override settings? → N

3. SET ENVIRONMENT VARIABLES
   → Run these commands (replace <RENDER_API_URL> with your Render URL):

   vercel env add NEXT_PUBLIC_API_URL production
   → Enter: https://kerjapedia-api.onrender.com

   vercel env add API_INTERNAL_URL production
   → Enter: https://kerjapedia-api.onrender.com

   vercel env add NEXT_PUBLIC_GOOGLE_CLIENT_ID production
   → Enter: 313607429666-14jgl98127ur6kdcsf04op2ujr59a370.apps.googleusercontent.com

4. DEPLOY TO PRODUCTION
   → Run: vercel --prod

5. VERIFY
   → Your web URL will be: https://kerjapedia-web.vercel.app
   → Open the URL and test login
""")


def test_api(api_url: str):
    """Test the deployed API."""
    print(f"\nTesting API at: {api_url}")

    # Test health
    try:
        health = api_call(f"{api_url}/health")
        print(f"  /health: {health.get('status', 'FAIL')}")
    except Exception as e:
        print(f"  /health: FAIL - {e}")
        return False

    # Test ready
    try:
        ready = api_call(f"{api_url}/ready")
        print(f"  /ready: {ready.get('status', 'FAIL')}")
    except Exception as e:
        print(f"  /ready: FAIL - {e}")

    # Test auth
    try:
        from dotenv import load_dotenv
        import os
        load_dotenv()
        email = os.getenv("ADMIN_EMAIL", "admin@kerjapedia.ai")
        password = os.getenv("ADMIN_PASSWORD", "admin23")
        result = api_call(
            f"{api_url}/auth/login",
            method="POST",
            body={"email": email, "password": password},
        )
        if result.get("access_token"):
            print(f"  /auth/login: OK (token received)")
        else:
            print(f"  /auth/login: FAIL - no token")
    except Exception as e:
        print(f"  /auth/login: FAIL - {e}")

    print("\nAPI test complete.")
    return True


def main():
    parser = argparse.ArgumentParser(description="KerjaPedia AI Deployment Helper")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup-render", help="Print Render deployment instructions")
    sub.add_parser("setup-vercel", help="Print Vercel deployment instructions")

    test_parser = sub.add_parser("test-api", help="Test deployed API")
    test_parser.add_argument("api_url", help="API URL (e.g., https://kerjapedia-api.onrender.com)")

    args = parser.parse_args()
    if args.command == "setup-render":
        setup_render()
    elif args.command == "setup-vercel":
        setup_vercel()
    elif args.command == "test-api":
        test_api(args.api_url)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
