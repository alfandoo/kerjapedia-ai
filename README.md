# KerjaPedia AI

KerjaPedia AI adalah asisten regulasi ketenagakerjaan Indonesia berbasis Retrieval-Augmented Generation (RAG). Produk ini membantu pengguna mencari, memahami, dan memverifikasi jawaban berdasarkan dokumen resmi yang tersimpan di `dataset/`.

## Status Project

Project sudah memiliki MVP RAG lokal dan jalur RAG industri berbasis provider:

- Mode lokal/offline: artifact ingestion + hash embedding + answer composer deterministik.
- Mode industri: Pinecone vector database + local BGE-M3 embedding + Groq chat completions.

Dokumen produk utama tersedia di `docs/PRD_KerjaPedia_AI.md`, roadmap pengerjaan tersedia di `docs/project/ROADMAP.md`, dan arsitektur RAG provider tersedia di `docs/RAG_PIPELINE.md`.

## Stack Awal

- Frontend: Next.js
- Backend API: Python FastAPI
- Database: PostgreSQL
- Vector store: Pinecone untuk mode industri, artifact lokal untuk development/test
- Embedding: BGE-M3 lokal untuk mode industri, hash embedding untuk development/test
- LLM provider: Groq untuk mode industri, local answer composer untuk development/test

## Struktur Folder

- `apps/web/` untuk aplikasi frontend.
- `apps/api/` untuk backend API.
- `packages/` untuk utilitas bersama.
- `scripts/` untuk ingestion, indexing, dan evaluasi.
- `docs/` untuk dokumentasi produk dan teknis.
- `dataset/` untuk dokumen regulasi sumber.

## Menjalankan Project

### Local Infrastructure

Copy environment contoh bila ingin menjalankan service lokal:

```bash
copy .env.example .env
docker compose up -d
```

Service lokal:

- PostgreSQL + pgvector: `localhost:5432`
- Redis: `localhost:6379`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`

Untuk mode industri, isi minimal variabel berikut di `.env`:

```bash
VECTOR_STORE=pinecone
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=kerjapedia-regulations
PINECONE_NAMESPACE=production
EMBEDDING_PROVIDER=bge_m3
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
LLM_PROVIDER=groq
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
```

Matikan service lokal:

```bash
docker compose down
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

Frontend berjalan di `http://localhost:3000`.

### Backend

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend health check tersedia di `http://127.0.0.1:8000/health`.
OpenAPI tersedia di `http://127.0.0.1:8000/docs`. Lihat `docs/API.md` untuk daftar endpoint MVP.

Jalankan migration database:

```bash
cd apps/api
.venv\Scripts\python -m alembic upgrade head
```

### Verifikasi Awal

```bash
cd apps/web
npm run lint
npm run format:check
npm run build

cd ../api
.venv\Scripts\python -m ruff check app tests
.venv\Scripts\python -m pytest
```

Jalankan end-to-end test frontend:

```bash
cd apps/web
npx playwright install chromium
npm run test:e2e
```

Lihat `docs/TESTING.md` untuk cakupan unit, integration, E2E, refusal, dan target latency.

### Ingestion Dataset

```bash
cd apps/api
.venv\Scripts\python -m app.services.ingestion.cli --document-id PP-35-2021
```

Ingest seluruh dataset ke Pinecone dengan BGE-M3:

```bash
cd apps/api
.venv\Scripts\python -m app.services.ingestion.cli --all --vector-store pinecone --embedding-provider bge_m3
```

Artifact ingestion tetap disimpan di `storage/ingestion/`. Lihat `docs/INGESTION_PIPELINE.md` untuk detail pipeline dan opsi `--persist-db`.

### Retrieval Lokal

```bash
cd apps/api
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Retrieval lokal membaca artifact di `storage/ingestion/`. Lihat `docs/RETRIEVAL.md` untuk detail scoring dan ranking.

Retrieval Pinecone:

```bash
cd apps/api
.venv\Scripts\python -m app.services.retrieval.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store pinecone
```

### Answer Generation Lokal

```bash
cd apps/api
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?"
```

Answer generation lokal membuat response terstruktur berisi `answer`, `citations`, `confidence`, `related_documents`, `refusal_reason`, dan disclaimer. Lihat `docs/ANSWER_GENERATION.md` untuk detail prompt, citation, dan guardrail.

Answer generation Groq:

```bash
cd apps/api
.venv\Scripts\python -m app.services.answering.cli "Apakah pekerja PKWT memperoleh kompensasi?" --vector-store pinecone --llm-provider groq
```

### Evaluasi RAG

```bash
cd apps/api
.venv\Scripts\python -m app.services.evaluation.cli --dataset ../../evaluation/golden_questions.json --storage-root ../../storage/ingestion --output ../../storage/evaluation/report.json --top-k 5
```

Evaluasi membandingkan mode baseline, dense, hybrid, dan rerank pada 150 pertanyaan seed. Dataset masih memerlukan verifikasi hukum manusia sebelum dipakai sebagai klaim kualitas produksi. Lihat `docs/EVALUATION.md` untuk metrik dan quality gate.

### Pre-commit

```bash
apps\api\.venv\Scripts\python -m pre_commit install
apps\api\.venv\Scripts\python -m pre_commit run --all-files
```

### Backup Metadata PostgreSQL

Setelah service PostgreSQL Docker aktif, buat backup sekaligus uji restore ke database
sementara:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1 -VerifyRestore
```

Lihat `docs/SECURITY.md` untuk konfigurasi production, retry ingestion, retention, dan
prosedur backup.

### Deployment Production

Salin `.env.production.example` menjadi `.env.production`, isi seluruh credential dan
URL HTTPS, lalu jalankan:

```powershell
docker compose -f compose.production.yaml --env-file .env.production up -d --build
python scripts/smoke_deployment.py --api-url https://api.example.com --web-url https://app.example.com
```

Panduan container, migration, GHCR, smoke test, dan rollback tersedia di
`docs/DEPLOYMENT.md`.

## Catatan Hukum

KerjaPedia AI bukan pengganti advokat, konsultan hukum, mediator hubungan industrial, atau instansi pemerintah. Jawaban harus selalu berbasis sumber resmi dan menyertakan citation yang dapat diverifikasi.
