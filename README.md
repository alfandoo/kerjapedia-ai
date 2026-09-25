# KerjaPedia AI

An AI-powered assistant for Indonesian employment regulations, built with Retrieval-Augmented Generation (RAG). Helps users search, understand, and verify answers from official regulation documents sourced from the Indonesian Audit Board (BPK) database.

**Live:** [kerjapedia-web.vercel.app](https://kerjapedia-web.vercel.app)

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js (Vercel) |
| Backend | Python FastAPI modular monolith (Render) |
| Database | Neon PostgreSQL (relational system of record) |
| Object Storage | Supabase Storage only (PDF/artifacts, private bucket) |
| Vector Store | Upstash Vector HYBRID (dense text-embedding-3-small + BM25) |
| Cache/Queue | Upstash Redis (Celery queue/cache/rate-limit) |
| Async Worker | Celery Worker (Render `kerjapedia-worker`) |
| LLM | Groq (openai/gpt-oss-120b) |
| Auth | Google OAuth (via Supabase Auth) + Bearer + RBAC (backend authority) |

## Features

- Chat with regulation retrieval for Indonesian employment law
- Citation tracking (article, clause, page, source)
- Admin dashboard (document management, evaluation, feedback)
- Hybrid search (dense + sparse embedding)
- Heuristic reranker
- Claim verification (LLM-backed)
- Multi-language support (ID/EN)

## Project Structure

```
apps/web/          Next.js frontend
apps/api/          FastAPI backend
dataset/           Regulation metadata (PDFs ignored)
docs/              Product & technical documentation
evaluation/        RAG evaluation scripts
scripts/           Utility scripts
```

## Local Development

### Prerequisites

- Node.js 18+
- Python 3.11+
- Docker (for Redis)

### Setup

```bash
# Clone
git clone https://github.com/alfandoo/kerjapedia-ai.git
cd kerjapedia-ai

# Copy environment
cp .env.example .env
# Fill in required variables (see .env.example)

# Start Redis
docker compose up -d

# Frontend
cd apps/web
npm install
npm run dev

# Backend
cd apps/api
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app --reload
```

Frontend: `http://localhost:3000`
Backend: `http://127.0.0.1:8000/docs`

### Environment Variables

Minimal for production mode:

```bash
VECTOR_STORE=upstash_vector
UPSTASH_VECTOR_REST_URL=
UPSTASH_VECTOR_REST_TOKEN=
LLM_PROVIDER=groq
GROQ_API_KEY=
```

See `.env.example` for the full list.

## Testing

```bash
# Frontend
cd apps/web
npm run lint
npm run build
npm run test:e2e

# Backend
cd apps/api
ruff check app tests
pytest
```

## Deployment

Auto-deploys on push to `main`:

- **Frontend** → Vercel
- **Backend** → Render

```bash
git push origin main
```

See `docs/DEPLOYMENT.md` for the full guide.

## Cost

| Service | Plan | Cost |
|---------|------|------|
| Vercel | Hobby | $0/month |
| Render | Free | $0/month |
| Supabase | Free | $0/month |
| Upstash | Free | $0/month |
| Groq | Free tier | $0-5/month |
| **Total** | | **$0-5/month** |

## Documentation

- [PRD](docs/PRD_KerjaPedia_AI.md) - Product Requirements
- [Architecture](docs/ARCHITECTURE.md) - System design
- [Deployment](docs/DEPLOYMENT.md) - Deploy guide
- [API](docs/API.md) - Endpoint reference
- [RAG Pipeline](docs/RAG_PIPELINE.md) - Retrieval & generation
- [Ingestion](docs/INGESTION_PIPELINE.md) - Document processing
- [Evaluation](docs/EVALUATION.md) - RAG evaluation
- [Testing](docs/TESTING.md) - Test coverage

## Disclaimer

KerjaPedia AI is not a substitute for legal counsel, industrial relations mediators, or government agencies. Answers should always be based on official sources with verifiable citations.
