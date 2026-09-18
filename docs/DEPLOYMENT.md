# Deployment Guide

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Vercel        │     │   Render        │
│   (Web/Next.js) │────▶│   (API/FastAPI) │
│                 │     │                 │
│  - Frontend     │     │  - Auth         │
│  - API Proxy    │     │  - Chat/RAG     │
│  - SSR Pages    │     │  - Admin API    │
└─────────────────┘     └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
              │ Supabase  │ │ Redis │ │ Upstash │
              │ (Postgres)│ │(Upstash)│ │(Vectors)│
              └───────────┘ └───────┘ └───────────┘
```

## Prerequisites

1. GitHub account with the repo pushed
2. Render account (free, no credit card needed)
3. Vercel account (already have)
4. All API keys ready (Supabase, Upstash Vector, Groq, Upstash Redis, SMTP)

## Step 1: Deploy API to Render

### 1.1 Login to Render

1. Go to https://dashboard.render.com
2. Click "Sign Up" → "GitHub" (authorize Render)
3. No credit card required for free tier

### 1.2 Create Blueprint

1. Click "New" → "Blueprint"
2. Connect repository: `alfandoo/kerjapedia-ai`
3. Render detects `render.yaml` automatically
4. Click "Apply" to create the service

### 1.3 Set Environment Variables

In Render Dashboard → your service → "Environment" tab:

Click "Add Environment Variable" for each:

| Key | Value | Source |
|-----|-------|--------|
| `SUPABASE_URL` | `https://ybfhmxjldxfdlxpfviuk.supabase.co` | .env |
| `SUPABASE_SERVICE_KEY` | (copy from .env) | .env |
| `SUPABASE_ANON_KEY` | (copy from .env) | .env |
| `DATABASE_URL` | (copy from .env) | .env |
| `REDIS_URL` | (copy from .env, Upstash) | .env |
| `OPENROUTER_API_KEY` | (copy from .env, fallback only) | .env |
| `GROQ_API_KEY` | (copy from .env) | .env |
| `UPSTASH_VECTOR_URL` | (copy from .env) | .env |
| `UPSTASH_VECTOR_TOKEN` | (copy from .env) | .env |
| `SMTP_USERNAME` | `kerjapedia@zohomail.com` | .env |
| `SMTP_PASSWORD` | (copy from .env) | .env |
| `SMTP_SENDER_EMAIL` | `kerjapedia@zohomail.com` | .env |

**Note:** `APP_ORIGIN` should be set to your Vercel URL after web deployment.

### 1.4 Wait for First Deploy

- First deploy: ~5-10 min (system deps + OCR toolchain)
- Subsequent deploys: ~2-3 min (Docker layer cache)
- Your API URL: `https://kerjapedia-api.onrender.com`

### 1.5 Run Database Migration

In Render Dashboard → your service → "Shell" tab:

```bash
python -m alembic upgrade head
```

### 1.6 Verify API

Open: `https://kerjapedia-api.onrender.com/health`

Should return:
```json
{"status": "ok"}
```

---

## Step 2: Deploy Web to Vercel

### 2.1 Login to Vercel

```bash
vercel login
```

### 2.2 Initialize Project

From the project root:

```bash
cd KerjaPediaAI
vercel
```

When prompted:
- Set up and deploy? → **Y**
- Which scope? → (your account)
- Link to existing project? → **N**
- Project name? → `kerjapedia-web`
- Directory where code is located? → `apps/web`
- Want to override settings? → **N**

### 2.3 Set Environment Variables

Replace `<RENDER_API_URL>` with your actual Render URL:

```bash
vercel env add NEXT_PUBLIC_API_URL production
# Paste: https://kerjapedia-api.onrender.com

vercel env add API_INTERNAL_URL production
# Paste: https://kerjapedia-api.onrender.com

vercel env add NEXT_PUBLIC_GOOGLE_CLIENT_ID production
# Paste: 313607429666-14jgl98127ur6kdcsf04op2ujr59a370.apps.googleusercontent.com
```

### 2.4 Deploy to Production

```bash
vercel --prod
```

### 2.5 Verify Web

Your web URL: `https://kerjapedia-web.vercel.app`

1. Open the URL
2. Test login with `admin@kerjapedia.ai`
3. Test chat with a question

---

## Step 3: Post-Deployment

### 3.1 Update APP_URL

In Render Dashboard → Environment → add:

```
APP_URL = https://kerjapedia-web.vercel.app
```

### 3.2 Update CORS

In Render Dashboard → Environment → add:

```
CORS_ORIGINS = https://kerjapedia-web.vercel.app
```

### 3.3 Enable Auto-Deploy

Both Render and Vercel auto-deploy on push to `main`.

---

## Troubleshooting

### API Cold Start

Free tier spins down after 15 min idle. First request takes ~30s.

**Workaround:** Use UptimeRobot (free) to ping `/health` every 5 min.

### API Build Fails

Check Render logs: Dashboard → your service → "Logs"

Common issues:
- Missing environment variables
- Docker build errors

### Web Can't Connect to API

1. Check `API_INTERNAL_URL` is set correctly in Vercel
2. Check CORS settings in Render
3. Test API directly: `curl https://kerjapedia-api.onrender.com/health`

### Upstash / Groq Connection Error

Retrieval answers `temporarily unavailable` right after deploy usually means:
1. `UPSTASH_VECTOR_URL` / `UPSTASH_VECTOR_TOKEN` mismatch (token must belong
   to the same index as the URL) — the API log shows
   `Upstash hybrid query failed: Unauthorized`.
2. `GROQ_API_KEY` missing — the log shows `GROQ_API_KEY is required`.
3. Startup `model provenance` errors are gone: production readiness now
   verifies the Upstash index contract (HYBRID/BM25/COSINE) via `/ready`.

---

## Cost

| Service | Plan | Cost |
|---------|------|------|
| Render (API) | Free | $0/month |
| Vercel (Web) | Hobby | $0/month |
| Supabase | Free | $0/month |
| Upstash Redis | Free | $0/month |
| Upstash Vector | Free | $0/month |
| Groq | Free tier / pay-as-you-go | $0-5/month |
| **Total** | | **$0-5/month** |

---

## Manual Deploy Commands

```bash
# Deploy API to Render (via git push)
git push origin main

# Deploy Web to Vercel
vercel --prod

# Test API
python scripts/deploy.py test-api https://kerjapedia-api.onrender.com
```
