# KerjaPedia AI

Asisten regulasi ketenagakerjaan Indonesia berbasis Retrieval-Augmented Generation (RAG). Membantu pengguna mencari, memahami, dan memverifikasi jawaban berdasarkan dokumen resmi dari Database Peraturan BPK.

**Live:** [kerjapedia-web.vercel.app](https://kerjapedia-web.vercel.app)

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js (Vercel) |
| Backend | Python FastAPI (Render) |
| Database | PostgreSQL via Supabase |
| Vector Store | Upstash Vector (hybrid: text-embedding-3-small + BM25) |
| Cache/Queue | Redis via Upstash |
| LLM | Groq (openai/gpt-oss-120b) |
| Auth | Google OAuth + HttpOnly cookies |

## Features

- Chat dengan retrieval regulasi ketenagakerjaan Indonesia
- Citation tracking (pasal, ayat, halaman, sumber)
- Admin dashboard (document management, evaluation, feedback)
- Hybrid search (dense + sparse embedding)
- Heuristic reranker
- Claim verification (LLM-backed)
- Multi-language support (ID/EN)

## Struktur Folder

```
apps/web/          Frontend Next.js
apps/api/          Backend FastAPI
dataset/           Metadata regulasi (PDF di-ignore)
docs/              Dokumentasi produk & teknis
evaluation/        Scripts evaluasi RAG
scripts/           Utility scripts
```

## Local Development

### Prerequisites

- Node.js 18+
- Python 3.11+
- Docker (untuk Redis)

### Setup

```bash
# Clone
git clone https://github.com/alfandoo/kerjapedia-ai.git
cd kerjapedia-ai

# Copy environment
cp .env.example .env
# Isi variabel yang diperlukan (lihat .env.example)

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

Minimal untuk mode industri:

```bash
VECTOR_STORE=upstash_vector
UPSTASH_VECTOR_REST_URL=
UPSTASH_VECTOR_REST_TOKEN=
LLM_PROVIDER=groq
GROQ_API_KEY=
```

Lihat `.env.example` untuk daftar lengkap.

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

Auto-deploy on push to `main`:

- **Frontend** → Vercel
- **Backend** → Render

```bash
git push origin main
```

Lihat `docs/DEPLOYMENT.md` untuk panduan lengkap.

## Cost

| Service | Plan | Cost |
|---------|------|------|
| Vercel | Hobby | $0/month |
| Render | Free | $0/month |
| Supabase | Free | $0/month |
| Upstash | Free | $0/month |
| Groq | Free tier | $0-5/month |
| **Total** | | **$0-5/month** |

## Dokumentasi

- [PRD](docs/PRD_KerjaPedia_AI.md) - Product Requirements
- [Architecture](docs/ARCHITECTURE.md) - System design
- [Deployment](docs/DEPLOYMENT.md) - Deploy guide
- [API](docs/API.md) - Endpoint reference
- [RAG Pipeline](docs/RAG_PIPELINE.md) - Retrieval & generation
- [Ingestion](docs/INGESTION_PIPELINE.md) - Document processing
- [Evaluation](docs/EVALUATION.md) - RAG evaluation
- [Testing](docs/TESTING.md) - Test coverage

## Catatan Hukum

KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator hubungan industrial, atau instansi pemerintah. Jawaban harus selalu berbasis sumber resmi dan menyertakan citation yang dapat diverifikasi.
